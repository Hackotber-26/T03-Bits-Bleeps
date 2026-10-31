"""
Threat Intelligence Manager & Local Threat Database
===================================================
Maintains a high-performance local SQLite database of malicious domains
sourced from threat intelligence feeds (PhishTank, OpenPhish, custom feeds).

Key Benefits:
- Zero DNS resolution latency: Lookups take microseconds via local SQLite indexes.
- No external HTTP calls during client queries.
- Complete resilience against external API rate limits or network downtime.
- Automated background synchronization worker with WAL mode.
- Audit logging of blocked DNS requests.
"""

from __future__ import annotations

import abc
import csv
import enum
import io
import json
import math
import os
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Generator, Iterable

from website_inspector import (
    AIInspectionResult,
    GemmaWebsiteInspector,
    NetworkTelemetry,
)


# ---------------------------------------------------------------------------
# Data Models: Risk Scoring & Threat Intelligence
# ---------------------------------------------------------------------------

class RiskLevel(str, enum.Enum):
    HIGH = "HIGH RISK"
    SUSPICIOUS = "SUSPICIOUS"
    LOW = "LOW RISK"


class RiskAction(str, enum.Enum):
    BLOCK = "Block"
    CAUTION = "Caution"
    ALLOW = "Allow"


@dataclass(frozen=True)
class ScoredRule:
    """Individual rule triggered during risk evaluation."""
    rule_id: str
    name: str
    points: int
    category: str  # "threat_feed", "heuristic", "whitelist"
    description: str


@dataclass(frozen=True)
class ThreatRecord:
    domain: str
    source: str
    threat_type: str
    details: str
    added_at: str | None = None
    updated_at: str | None = None


@dataclass
class RiskAssessment:
    """
    Comprehensive rule-based weighted risk assessment for a domain.
    Distinguishes confirmed threat-feed matches from heuristic suspicion.
    """
    domain: str
    risk_level: RiskLevel
    action: RiskAction
    score: int  # 0 to 100
    triggered_rules: list[ScoredRule] = field(default_factory=list)
    matched_feed_record: ThreatRecord | None = None
    matched_domain: str | None = None
    summary: str = ""
    reason: str = ""

    @property
    def is_blocked(self) -> bool:
        return self.action == RiskAction.BLOCK

    @property
    def record(self) -> ThreatRecord | None:
        return self.matched_feed_record


# Backward-compatibility alias
CheckResult = RiskAssessment


# ---------------------------------------------------------------------------
# Default Whitelist (Prevents False Positives on Core Internet Infrastructure)
# ---------------------------------------------------------------------------

DEFAULT_WHITELIST: set[str] = {
    "google.com", "gstatic.com", "googleapis.com", "googleusercontent.com", "gmail.com",
    "apple.com", "icloud.com", "mzstatic.com", "aaplimg.com",
    "microsoft.com", "live.com", "office.com", "office365.com", "azure.com", "windows.com", "bing.com", "msn.com",
    "amazon.com", "aws.amazon.com", "media-amazon.com",
    "cloudflare.com", "cloudflare-dns.com",
    "github.com", "githubusercontent.com", "gitlab.com",
    "youtube.com", "ytimg.com", "googlevideo.com",
    "facebook.com", "fbcdn.net", "instagram.com", "whatsapp.com",
    "twitter.com", "x.com", "t.co", "twimg.com",
    "linkedin.com", "licdn.com",
    "wikipedia.org", "wikimedia.org",
    "yahoo.com", "yimg.com",
    "netflix.com", "nflxvideo.net", "spotify.com",
    "reddit.com", "redditmedia.com",
}


def is_domain_whitelisted(domain: str, extra_whitelist: set[str] | None = None) -> bool:
    """
    Check if a domain or its parent domain is on the built-in or custom whitelist.
    Prevents innocent platforms (Google Docs, Apple, etc.) from being blocked
    due to user-submitted phish URLs on shared platforms.
    """
    domain = domain.lower().rstrip(".")
    if domain in DEFAULT_WHITELIST:
        return True
    if any(domain.endswith("." + w) for w in DEFAULT_WHITELIST):
        return True
    if extra_whitelist:
        if domain in extra_whitelist:
            return True
        if any(domain.endswith("." + w) for w in extra_whitelist):
            return True
    return False


# ---------------------------------------------------------------------------
# Domain Extraction & Candidate Generation Helpers
# ---------------------------------------------------------------------------

def extract_domain_from_url(url: str) -> str | None:
    """Extract clean lowercase domain/host from a URL or raw domain string."""
    if not url:
        return None
    url = url.strip()
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "http://" + url
    try:
        parts = urllib.parse.urlsplit(url)
        netloc = parts.netloc
        if not netloc:
            return None
        # Remove user:pass@ if present
        if "@" in netloc:
            netloc = netloc.split("@")[-1]
        # Remove port :8080 if present
        if ":" in netloc:
            netloc = netloc.split(":")[0]
        domain = netloc.lower().rstrip(".")
        if not domain or len(domain) > 253 or " " in domain:
            return None
        return domain
    except Exception:
        return None


def get_candidate_domains(domain: str) -> list[str]:
    """
    Generate domain and parent domain candidates for subdomain matching.
    e.g. 'sub.login.phish.com' -> ['sub.login.phish.com', 'login.phish.com', 'phish.com']
    Stops at 2-part domain to prevent matching bare TLDs like '.com'.
    """
    domain = domain.lower().rstrip(".")
    labels = domain.split(".")
    if len(labels) < 2:
        return [domain] if domain else []

    candidates = []
    for i in range(len(labels) - 1):
        candidates.append(".".join(labels[i:]))
    return candidates


# ---------------------------------------------------------------------------
# Rule-Based Weighted Scoring System (Transparent & Explainable)
# ---------------------------------------------------------------------------

# Frequently abused TLDs with high disposable spam/phishing rates
ABUSED_TLDS: set[str] = {
    "top", "xyz", "buzz", "click", "work", "lol", "country", "gq", "cf", "ml", "tk",
    "surf", "fit", "rest", "monster", "sbs", "cam", "zip", "mov", "su", "link",
}

# High-value brand names targeted in credential harvesting / impersonation
TARGET_BRANDS: set[str] = {
    "paypal", "appleid", "netflix", "microsoft", "amazon", "google", "facebook",
    "instagram", "whatsapp", "metamask", "binance", "coinbase", "chase",
    "wellsfargo", "bankofamerica", "steam", "telegram", "roblox", "tiktok", "outlook",
}

# Deceptive security, verification, and credential keywords
CREDENTIAL_KEYWORDS: set[str] = {
    "login", "signin", "sign-in", "log-in", "verify", "verification",
    "auth", "authenticate", "recovery", "support", "billing",
    "account-update", "wallet", "secure",
}

# Free dynamic DNS / public hosting / tunnel platforms frequently abused for disposable phishing
FREE_HOSTING_PROVIDERS: set[str] = {
    "duckdns.org", "ngrok-free.app", "ngrok.io", "loca.lt",
    "firebaseapp.com", "pages.dev", "weebly.com", "glitch.me", "000webhostapp.com",
}


def calculate_shannon_entropy(text: str) -> float:
    """Calculate Shannon entropy of a string (bits per symbol)."""
    if not text:
        return 0.0
    freq: dict[str, int] = {}
    for char in text:
        freq[char] = freq.get(char, 0) + 1
    length = len(text)
    return -sum((count / length) * math.log2(count / length) for count in freq.values())


def evaluate_domain_risk(
    domain: str,
    feed_match: tuple[str, ThreatRecord] | None = None,
    is_whitelisted: bool = False,
    ai_cache: AIInspectionResult | None = None,
) -> RiskAssessment:
    """
    Transparent Rule-Based Weighted Scoring Engine.

    Risk Tiers:
    - HIGH RISK (Score 100, Action: Block):
      Confirmed malicious domain from a trusted feed.
    - SUSPICIOUS (Score 35-75, Action: Caution):
      Suspicious characteristics without confirmed malicious evidence.
    - LOW RISK (Score 0-34, Action: Allow):
      No known threat detected. This does not guarantee that the domain is safe.
    """
    domain = domain.lower().rstrip(".")
    triggered_rules: list[ScoredRule] = []

    # 1. Whitelist Exemption (Overrides all threats and heuristics)
    if is_whitelisted:
        rule = ScoredRule(
            rule_id="WHITELIST_EXEMPTION",
            name="Whitelist Exemption",
            points=0,
            category="whitelist",
            description="Domain is on the verified system or user whitelist."
        )
        return RiskAssessment(
            domain=domain,
            risk_level=RiskLevel.LOW,
            action=RiskAction.ALLOW,
            score=0,
            triggered_rules=[rule],
            matched_feed_record=None,
            summary="Verified legitimate infrastructure or whitelisted domain.",
            reason="Whitelisted domain (Allow)",
        )

    # 2. Confirmed Threat-Feed Match (Threat Feed Category)
    if feed_match:
        matched_candidate, record = feed_match
        if matched_candidate == domain:
            desc = f"Exact match confirmed in {record.source} ({record.threat_type}): {record.details}"
        else:
            desc = f"Subdomain of confirmed malicious domain '{matched_candidate}' in {record.source} ({record.threat_type})"

        rule = ScoredRule(
            rule_id="CONFIRMED_FEED_MATCH",
            name="Confirmed Threat-Feed Match",
            points=100,
            category="threat_feed",
            description=desc,
        )
        triggered_rules.append(rule)
        return RiskAssessment(
            domain=domain,
            risk_level=RiskLevel.HIGH,
            action=RiskAction.BLOCK,
            score=100,
            triggered_rules=triggered_rules,
            matched_feed_record=record,
            matched_domain=matched_candidate,
            summary="Confirmed malicious domain from a trusted feed.",
            reason=desc,
        )

    # 3. Cached AI Inspection (Gemma-4-31b-it Multimodal Website Evaluation)
    if ai_cache:
        rule = ScoredRule(
            rule_id="GEMMA_AI_VERDICT",
            name=f"Gemma-4-31b-it Inspection",
            points=ai_cache.score,
            category="ai_inspection",
            description=f"AI Verdict: {ai_cache.verdict} (Score {ai_cache.score}/100) - {ai_cache.summary}"
        )
        triggered_rules.append(rule)
        for v in ai_cache.visual_indicators:
            triggered_rules.append(ScoredRule(
                rule_id="AI_VISUAL_INDICATOR",
                name="Visual Evidence",
                points=0,
                category="ai_inspection",
                description=v,
            ))
        for n in ai_cache.network_indicators:
            triggered_rules.append(ScoredRule(
                rule_id="AI_NETWORK_INDICATOR",
                name="Network Request Finding",
                points=0,
                category="ai_inspection",
                description=n,
            ))

        risk_level = RiskLevel.HIGH if ai_cache.score >= 75 else (RiskLevel.SUSPICIOUS if ai_cache.score >= 35 else RiskLevel.LOW)
        action = RiskAction.BLOCK if ai_cache.score >= 75 else (RiskAction.CAUTION if ai_cache.score >= 35 else RiskAction.ALLOW)

        return RiskAssessment(
            domain=domain,
            risk_level=risk_level,
            action=action,
            score=ai_cache.score,
            triggered_rules=triggered_rules,
            matched_feed_record=None,
            matched_domain=None,
            summary=ai_cache.summary,
            reason=f"AI Inspection Verdict: {ai_cache.verdict} (Score: {ai_cache.score}/100)",
        )

    # 3. Transparent Heuristic Rules (Heuristic Suspicion Category)
    labels = domain.split(".")
    tld = labels[-1] if labels else ""
    # Second-level label or primary hostname label (e.g. 'paypal-update' in 'paypal-update.xyz')
    main_label = labels[-2] if len(labels) >= 2 else (labels[0] if labels else "")

    # Rule: Suspicious / Abused TLD (+25 pts)
    if tld in ABUSED_TLDS:
        triggered_rules.append(ScoredRule(
            rule_id="SUSPICIOUS_TLD",
            name="Abused / High-Risk TLD",
            points=25,
            category="heuristic",
            description=f"Uses top-level domain '.{tld}' disproportionately abused for disposable campaigns."
        ))

    # Rule: Brand Impersonation on Unverified Domain (+35 pts)
    matched_brands = [b for b in TARGET_BRANDS if b in domain]
    if matched_brands:
        brand_list = ", ".join(matched_brands)
        triggered_rules.append(ScoredRule(
            rule_id="BRAND_IMPERSONATION",
            name="Target Brand Name Detected",
            points=35,
            category="heuristic",
            description=f"Contains high-value target brand '{brand_list}' on an unaffiliated domain."
        ))

    # Rule: Credential & Security Deception Terminology (+20 pts)
    matched_keywords = [k for k in CREDENTIAL_KEYWORDS if k in domain]
    if len(matched_keywords) >= 2 or (matched_brands and matched_keywords) or any("-" + k in domain or k + "-" in domain for k in matched_keywords):
        kw_list = ", ".join(matched_keywords[:4])
        triggered_rules.append(ScoredRule(
            rule_id="SECURITY_KEYWORDS",
            name="Deceptive Security / Credential Keywords",
            points=20,
            category="heuristic",
            description=f"Contains deceptive authentication/security keywords: {kw_list}."
        ))

    # Rule: Punycode / IDN Homograph (+30 pts)
    if any(label.startswith("xn--") for label in labels):
        triggered_rules.append(ScoredRule(
            rule_id="PUNYCODE_HOMOGRAPH",
            name="Internationalized Domain Name (Punycode)",
            points=30,
            category="heuristic",
            description="Domain contains Punycode ('xn--'), often used to visually mimic characters in homograph attacks."
        ))

    # Rule: High Shannon Entropy / DGA Pattern (+20 pts)
    entropy = calculate_shannon_entropy(main_label)
    if len(main_label) >= 9 and entropy >= 3.4:
        triggered_rules.append(ScoredRule(
            rule_id="HIGH_ENTROPY_DGA",
            name="High Entropy / DGA Pattern",
            points=20,
            category="heuristic",
            description=f"Label '{main_label}' exhibits high Shannon entropy ({entropy:.2f}), suggestive of automated DGA or randomized generation."
        ))

    # Rule: Excessive Subdomain Depth or Hyphen Chaining (+15 pts)
    hyphen_count = domain.count("-")
    subdomain_depth = len(labels)
    if subdomain_depth >= 4 or hyphen_count >= 3:
        reasons = []
        if subdomain_depth >= 4:
            reasons.append(f"{subdomain_depth} subdomain levels")
        if hyphen_count >= 3:
            reasons.append(f"{hyphen_count} hyphens")
        triggered_rules.append(ScoredRule(
            rule_id="EXCESSIVE_SUBDOMAINS",
            name="Excessive Subdomain Depth / Hyphen Chaining",
            points=15,
            category="heuristic",
            description=f"Unusual domain structure with {', '.join(reasons)}."
        ))

    # Rule: Free Public Hosting / Tunnel Subdomain Abuse (+25 pts)
    for provider in FREE_HOSTING_PROVIDERS:
        if domain.endswith("." + provider) and (matched_brands or matched_keywords or hyphen_count >= 2):
            triggered_rules.append(ScoredRule(
                rule_id="FREE_HOSTING_ABUSE",
                name="Abused Free Hosting / Tunnel Platform",
                points=25,
                category="heuristic",
                description=f"Hosted on free cloud/tunnel provider '{provider}' with suspicious subdomains."
            ))
            break

    # Calculate Heuristic Score (Capped at 75 max; heuristics alone can NEVER reach HIGH RISK / Block)
    raw_score = sum(r.points for r in triggered_rules)
    score = min(75, raw_score)

    if score >= 35:
        risk_level = RiskLevel.SUSPICIOUS
        action = RiskAction.CAUTION
        summary = "Suspicious characteristics without confirmed malicious evidence."
        reason = f"Suspicious characteristics detected (Score: {score}/100)"
    else:
        risk_level = RiskLevel.LOW
        action = RiskAction.ALLOW
        summary = "No known threat detected. This does not guarantee that the domain is safe."
        reason = f"No known threat detected (Score: {score}/100)"

    return RiskAssessment(
        domain=domain,
        risk_level=risk_level,
        action=action,
        score=score,
        triggered_rules=triggered_rules,
        matched_feed_record=None,
        matched_domain=None,
        summary=summary,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Local SQLite Threat Database
# ---------------------------------------------------------------------------

class ThreatDatabase:
    """
    High-performance, thread-safe SQLite threat database.
    Uses Write-Ahead Logging (WAL) so concurrent DNS query threads can read
    without locking or being blocked by background sync writers.
    """

    def __init__(self, db_path: str = "threats.db"):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            self._local.conn = conn
        return self._local.conn

    def _init_db(self) -> None:
        """Create tables and indexes if they do not exist."""
        conn = self._get_connection()
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS threats (
                    domain TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    threat_type TEXT NOT NULL,
                    details TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_threats_source ON threats (source);
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_threats_type ON threats (threat_type);
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS feed_sync_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    feed_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    records_imported INTEGER DEFAULT 0,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    client_ip TEXT NOT NULL,
                    domain TEXT NOT NULL,
                    matched_domain TEXT NOT NULL,
                    query_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    threat_type TEXT NOT NULL,
                    score INTEGER DEFAULT 0,
                    risk_level TEXT DEFAULT '',
                    action TEXT DEFAULT '',
                    rules TEXT DEFAULT '',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Auto-migrate columns if table already existed without them
            for col, col_type in [("score", "INTEGER DEFAULT 0"), ("risk_level", "TEXT DEFAULT ''"), ("action", "TEXT DEFAULT ''"), ("rules", "TEXT DEFAULT ''")]:
                try:
                    conn.execute(f"ALTER TABLE query_audit_log ADD COLUMN {col} {col_type};")
                except Exception:
                    pass
            conn.execute("""
                CREATE TABLE IF NOT EXISTS whitelist (
                    domain TEXT PRIMARY KEY,
                    reason TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ai_inspection_cache (
                    domain TEXT PRIMARY KEY,
                    score INTEGER NOT NULL,
                    verdict TEXT NOT NULL,
                    is_safe INTEGER NOT NULL,
                    risk_level TEXT NOT NULL,
                    impersonated_brand TEXT,
                    summary TEXT,
                    visual_indicators TEXT,
                    network_indicators TEXT,
                    screenshot_path TEXT,
                    network_info_json TEXT,
                    model_name TEXT,
                    inspected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at REAL
                );
            """)

    def save_ai_inspection(self, domain: str, result: AIInspectionResult, ttl_seconds: int = 86400) -> None:
        """
        Store AI inspection results in the cache database.
        If verdict is Block or score >= 75, automatically registers the domain in the
        threats table so subsequent DNS queries are blocked immediately.
        """
        domain = domain.lower().rstrip(".")
        if not domain:
            return

        conn = self._get_connection()
        now = time.time()
        expires_at = now + ttl_seconds
        vis_json = json.dumps(result.visual_indicators)
        net_json = json.dumps(result.network_indicators)
        telemetry_json = json.dumps(asdict(result.network_telemetry)) if result.network_telemetry else "{}"

        with conn:
            conn.execute("""
                INSERT INTO ai_inspection_cache (
                    domain, score, verdict, is_safe, risk_level, impersonated_brand,
                    summary, visual_indicators, network_indicators, screenshot_path,
                    network_info_json, model_name, inspected_at, expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
                ON CONFLICT(domain) DO UPDATE SET
                    score=excluded.score,
                    verdict=excluded.verdict,
                    is_safe=excluded.is_safe,
                    risk_level=excluded.risk_level,
                    impersonated_brand=excluded.impersonated_brand,
                    summary=excluded.summary,
                    visual_indicators=excluded.visual_indicators,
                    network_indicators=excluded.network_indicators,
                    screenshot_path=excluded.screenshot_path,
                    network_info_json=excluded.network_info_json,
                    model_name=excluded.model_name,
                    inspected_at=CURRENT_TIMESTAMP,
                    expires_at=excluded.expires_at;
            """, (
                domain, result.score, result.verdict, 1 if result.is_safe else 0,
                result.risk_level, result.impersonated_brand, result.summary,
                vis_json, net_json, result.screenshot_path, telemetry_json,
                result.model_name, expires_at,
            ))

            # Store blocking info into active threat database if flagged as malicious
            if result.verdict == "Block" or result.score >= 75:
                brand_detail = f" (impersonating {result.impersonated_brand})" if result.impersonated_brand else ""
                details = f"AI Verdict: Block (Score {result.score}/100){brand_detail} - {result.summary}"
                conn.execute("""
                    INSERT INTO threats (domain, source, threat_type, details, added_at, updated_at)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT(domain) DO UPDATE SET
                        source=excluded.source,
                        threat_type=excluded.threat_type,
                        details=excluded.details,
                        updated_at=CURRENT_TIMESTAMP;
                """, (domain, f"Gemma-AI ({result.model_name})", "phishing_impersonation", details))

    def get_cached_ai_inspection(self, domain: str) -> AIInspectionResult | None:
        """Fetch cached AI inspection if present and unexpired."""
        domain = domain.lower().rstrip(".")
        conn = self._get_connection()
        cursor = conn.cursor()
        now = time.time()
        cursor.execute("""
            SELECT domain, score, verdict, is_safe, risk_level, impersonated_brand,
                   summary, visual_indicators, network_indicators, screenshot_path,
                   model_name, inspected_at, expires_at
            FROM ai_inspection_cache
            WHERE domain = ? AND expires_at > ?
        """, (domain, now))
        row = cursor.fetchone()
        if not row:
            return None

        try:
            visual_inds = json.loads(row["visual_indicators"]) if row["visual_indicators"] else []
        except Exception:
            visual_inds = []

        try:
            network_inds = json.loads(row["network_indicators"]) if row["network_indicators"] else []
        except Exception:
            network_inds = []

        return AIInspectionResult(
            domain=row["domain"],
            is_safe=bool(row["is_safe"]),
            score=int(row["score"]),
            verdict=row["verdict"],
            risk_level=row["risk_level"],
            impersonated_brand=row["impersonated_brand"],
            summary=row["summary"] or "",
            visual_indicators=visual_inds,
            network_indicators=network_inds,
            screenshot_path=row["screenshot_path"],
            model_name=row["model_name"] or "gemma-4-31b-it",
            inspected_at=row["inspected_at"],
        )

    def get_custom_whitelist(self) -> set[str]:
        """Fetch all user-whitelisted domains from the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT domain FROM whitelist")
        return {row[0] for row in cursor.fetchall()}

    def add_to_whitelist(self, domain: str, reason: str = "User added") -> None:
        """Add domain to whitelist and remove from threats table."""
        domain = domain.lower().rstrip(".")
        if not domain:
            return
        conn = self._get_connection()
        with conn:
            conn.execute("""
                INSERT INTO whitelist (domain, reason) VALUES (?, ?)
                ON CONFLICT(domain) DO UPDATE SET reason=excluded.reason;
            """, (domain, reason))
            conn.execute("DELETE FROM threats WHERE domain = ? OR domain LIKE ?", (domain, "%." + domain))

    def remove_from_whitelist(self, domain: str) -> bool:
        """Remove domain from whitelist."""
        domain = domain.lower().rstrip(".")
        conn = self._get_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM whitelist WHERE domain = ?", (domain,))
            return cursor.rowcount > 0

    def match_domain(self, domain: str) -> tuple[str, ThreatRecord] | None:
        """
        Fast lookup against local threat database.
        Checks exact domain and parent candidate domains (for subdomain matching).
        Returns (matched_candidate, ThreatRecord) or None.
        """
        # Always check whitelist first
        user_wl = self.get_custom_whitelist()
        if is_domain_whitelisted(domain, user_wl):
            return None
        candidates = get_candidate_domains(domain)
        if not candidates:
            return None

        conn = self._get_connection()
        placeholders = ",".join("?" for _ in candidates)
        # Query order by length of candidate descending so the most specific match wins
        sql = f"""
            SELECT domain, source, threat_type, details, added_at, updated_at
            FROM threats
            WHERE domain IN ({placeholders})
        """
        cursor = conn.cursor()
        cursor.execute(sql, candidates)
        rows = cursor.fetchall()
        if not rows:
            return None

        # Build map for fast prioritization
        row_map = {row["domain"]: row for row in rows}
        for cand in candidates:
            if cand in row_map:
                row = row_map[cand]
                record = ThreatRecord(
                    domain=row["domain"],
                    source=row["source"],
                    threat_type=row["threat_type"],
                    details=row["details"] or "",
                    added_at=row["added_at"],
                    updated_at=row["updated_at"],
                )
                return cand, record
        return None

    def upsert_threat(self, domain: str, source: str, threat_type: str, details: str = "") -> None:
        """Add or update a single domain threat record."""
        domain = domain.lower().rstrip(".")
        if not domain:
            return
        conn = self._get_connection()
        with conn:
            conn.execute("""
                INSERT INTO threats (domain, source, threat_type, details, added_at, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(domain) DO UPDATE SET
                    source=excluded.source,
                    threat_type=excluded.threat_type,
                    details=excluded.details,
                    updated_at=CURRENT_TIMESTAMP;
            """, (domain, source, threat_type, details))

    def bulk_upsert_threats(self, records: Iterable[tuple[str, str, str, str]]) -> int:
        """
        Bulk insert or update threats inside a single transaction.
        records: Iterable of (domain, source, threat_type, details)
        """
        conn = self._get_connection()
        count = 0
        with conn:
            cursor = conn.cursor()
            cursor.executemany("""
                INSERT INTO threats (domain, source, threat_type, details, added_at, updated_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(domain) DO UPDATE SET
                    source=excluded.source,
                    threat_type=excluded.threat_type,
                    details=excluded.details,
                    updated_at=CURRENT_TIMESTAMP;
            """, records)
            count = cursor.rowcount
        return count

    def delete_threat(self, domain: str) -> bool:
        """Remove a domain from the threat database."""
        domain = domain.lower().rstrip(".")
        conn = self._get_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM threats WHERE domain = ?", (domain,))
            return cursor.rowcount > 0

    def clear_source(self, source: str) -> int:
        """Remove all records from a specific feed source."""
        conn = self._get_connection()
        with conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM threats WHERE source = ?", (source,))
            return cursor.rowcount

    def log_audit(
        self,
        client_ip: str,
        domain: str,
        matched_domain: str,
        query_type: str,
        source: str,
        threat_type: str,
        score: int = 0,
        risk_level: str = "",
        action: str = "",
        rules: str = "",
    ) -> None:
        """Log a security event (Block or Caution) for auditing."""
        conn = self._get_connection()
        with conn:
            conn.execute("""
                INSERT INTO query_audit_log (
                    client_ip, domain, matched_domain, query_type, source, threat_type,
                    score, risk_level, action, rules
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (client_ip, domain, matched_domain, query_type, source, threat_type, score, risk_level, action, rules))

    def record_sync(self, feed_name: str, status: str, count: int, error_message: str | None = None) -> None:
        """Record the outcome of a feed synchronization."""
        conn = self._get_connection()
        with conn:
            conn.execute("""
                INSERT INTO feed_sync_history (feed_name, status, records_imported, error_message)
                VALUES (?, ?, ?, ?);
            """, (feed_name, status, count, error_message))

    def get_stats(self) -> dict:
        """Retrieve overview statistics from the threat database."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM threats")
        total_threats = cursor.fetchone()[0]

        cursor.execute("SELECT source, COUNT(*) as cnt FROM threats GROUP BY source ORDER BY cnt DESC")
        sources_breakdown = {row["source"]: row["cnt"] for row in cursor.fetchall()}

        cursor.execute("SELECT threat_type, COUNT(*) as cnt FROM threats GROUP BY threat_type ORDER BY cnt DESC")
        types_breakdown = {row["threat_type"]: row["cnt"] for row in cursor.fetchall()}

        cursor.execute("SELECT COUNT(*) FROM query_audit_log")
        total_logged_events = cursor.fetchone()[0]

        cursor.execute("""
            SELECT feed_name, status, records_imported, synced_at, error_message
            FROM feed_sync_history
            ORDER BY id DESC LIMIT 10
        """)
        recent_syncs = [dict(row) for row in cursor.fetchall()]

        return {
            "total_threats": total_threats,
            "sources": sources_breakdown,
            "threat_types": types_breakdown,
            "total_blocked_queries": total_logged_events,
            "recent_syncs": recent_syncs,
        }

    def get_recent_audit_logs(self, limit: int = 25) -> list[dict]:
        """Fetch latest security audit logs."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, client_ip, domain, matched_domain, query_type, source, threat_type,
                   score, risk_level, action, rules, timestamp
            FROM query_audit_log
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]

    def close(self) -> None:
        """Close open database connections on this thread."""
        if hasattr(self._local, "conn") and self._local.conn is not None:
            try:
                self._local.conn.close()
            except Exception:
                pass
            self._local.conn = None


# ---------------------------------------------------------------------------
# Threat Feeds (Abstract Base Class & Implementations)
# ---------------------------------------------------------------------------

class ThreatFeed(abc.ABC):
    """
    Abstract base class for periodic threat intelligence feed fetchers.
    Subclasses fetch threat data in bulk and yield (domain, details).
    """
    name: str = "BaseFeed"
    threat_type: str = "malicious"
    enabled: bool = True

    @abc.abstractmethod
    def fetch_records(self) -> Generator[tuple[str, str], None, None]:
        """
        Fetch records from feed source.
        Yields: (domain, details)
        """
        pass


class PhishTankFeed(ThreatFeed):
    """
    Fetches verified active phishing records in bulk from PhishTank's database feed.
    Default feed: http://data.phishtank.com/data/online-valid.csv
    """
    name = "PhishTank"
    threat_type = "phishing"

    def __init__(
        self,
        api_key: str | None = None,
        feed_url: str | None = None,
        user_agent: str | None = None,
        timeout: float = 30.0,
        enabled: bool = True,
    ):
        self.api_key = api_key or os.getenv("PHISHTANK_API_KEY")
        if feed_url:
            self.feed_url = feed_url
        elif self.api_key:
            self.feed_url = f"http://data.phishtank.com/data/{self.api_key}/online-valid.csv"
        else:
            self.feed_url = "http://data.phishtank.com/data/online-valid.csv"

        self.user_agent = user_agent or os.getenv("PHISHTANK_USER_AGENT", "phishtank/odikyu-dns")
        self.timeout = timeout
        self.enabled = enabled

    def fetch_records(self) -> Generator[tuple[str, str], None, None]:
        request = urllib.request.Request(
            self.feed_url,
            headers={
                "User-Agent": self.user_agent,
                "Accept-Encoding": "identity",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            reader = csv.DictReader(io.StringIO(content))
            seen_domains = set()

            for row in reader:
                url = row.get("url")
                if not url:
                    continue
                domain = extract_domain_from_url(url)
                if not domain or domain in seen_domains:
                    continue
                seen_domains.add(domain)

                phish_id = row.get("phish_id", "")
                target = row.get("target", "Unknown")
                details = f"Target: {target}, PhishID: {phish_id}"
                yield domain, details


class OpenPhishFeed(ThreatFeed):
    """
    Fetches active phishing URLs from OpenPhish Community Feed.
    Default feed: https://openphish.com/feed.txt
    """
    name = "OpenPhish"
    threat_type = "phishing"

    def __init__(
        self,
        feed_url: str = "https://openphish.com/feed.txt",
        user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) odikyu-dns/1.0",
        timeout: float = 20.0,
        enabled: bool = True,
    ):
        self.feed_url = feed_url
        self.user_agent = user_agent
        self.timeout = timeout
        self.enabled = enabled

    def fetch_records(self) -> Generator[tuple[str, str], None, None]:
        request = urllib.request.Request(
            self.feed_url,
            headers={"User-Agent": self.user_agent},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
            seen_domains = set()
            for line in content.splitlines():
                url_str = line.strip()
                if not url_str or url_str.startswith("#"):
                    continue
                domain = extract_domain_from_url(url_str)
                if not domain or domain in seen_domains:
                    continue
                seen_domains.add(domain)
                yield domain, f"Reported Phish: {url_str[:60]}"


class LocalListFeed(ThreatFeed):
    """
    Feed loaded from a local text file or memory set of domains.
    Format: one domain per line (comments starting with # are ignored).
    """
    name = "LocalList"
    threat_type = "custom"

    def __init__(
        self,
        file_path: str | None = None,
        domains: Iterable[str] | None = None,
        threat_type: str = "custom",
        name: str = "LocalBlocklist",
        enabled: bool = True,
    ):
        self.file_path = file_path
        self.domains = list(domains or [])
        self.threat_type = threat_type
        self.name = name
        self.enabled = enabled

    def fetch_records(self) -> Generator[tuple[str, str], None, None]:
        seen = set()
        for d in self.domains:
            dom = extract_domain_from_url(d) or d.lower().strip()
            if dom and dom not in seen:
                seen.add(dom)
                yield dom, "Manual blocklist entry"

        if self.file_path and os.path.exists(self.file_path):
            with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    dom = extract_domain_from_url(line) or line.lower()
                    if dom and dom not in seen:
                        seen.add(dom)
                        yield dom, f"File source: {os.path.basename(self.file_path)}"


# ---------------------------------------------------------------------------
# Threat Intelligence Manager (Coordinator & Background Sync Worker)
# ---------------------------------------------------------------------------

class ThreatIntelligenceManager:
    """
    Coordinates local threat database, feed synchronization, background worker,
    and ultra-fast domain checking for the DNS Proxy.
    """

    def __init__(self, db_path: str = "threats.db"):
        self.db = ThreatDatabase(db_path)
        self.feeds: dict[str, ThreatFeed] = {}
        self.inspector = GemmaWebsiteInspector()
        self._sync_lock = threading.Lock()
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def register_feed(self, feed: ThreatFeed) -> None:
        """Register a threat feed source."""
        self.feeds[feed.name] = feed

    def sync_feed(self, feed_name: str) -> int:
        """Synchronize a single feed into the local database."""
        feed = self.feeds.get(feed_name)
        if not feed:
            raise ValueError(f"Unknown feed: {feed_name}")
        if not feed.enabled:
            return 0

        print(f"[*] Syncing threat feed: {feed.name} ...")
        start_time = time.time()
        try:
            records_batch = []
            total_imported = 0
            user_wl = self.db.get_custom_whitelist()
            for domain, details in feed.fetch_records():
                if is_domain_whitelisted(domain, user_wl):
                    continue
                records_batch.append((domain, feed.name, feed.threat_type, details))
                if len(records_batch) >= 2000:
                    self.db.bulk_upsert_threats(records_batch)
                    total_imported += len(records_batch)
                    records_batch.clear()

            if records_batch:
                self.db.bulk_upsert_threats(records_batch)
                total_imported += len(records_batch)

            elapsed = time.time() - start_time
            self.db.record_sync(feed.name, "SUCCESS", total_imported)
            print(f"[+] Feed '{feed.name}' synced: {total_imported} domains imported in {elapsed:.2f}s")
            return total_imported

        except Exception as exc:
            elapsed = time.time() - start_time
            err_msg = str(exc)
            self.db.record_sync(feed.name, "FAILED", 0, error_message=err_msg)
            print(f"[!] Error syncing feed '{feed.name}': {err_msg}")
            return 0

    def sync_all(self) -> dict[str, int]:
        """Synchronize all enabled registered feeds."""
        with self._sync_lock:
            results = {}
            for name, feed in self.feeds.items():
                if feed.enabled:
                    results[name] = self.sync_feed(name)
            return results

    def inspect_website(self, domain: str, force: bool = False) -> AIInspectionResult:
        """
        Run distinctive AI-powered website inspection with gemma-4-31b-it:
        Collects network telemetry, captures screenshot, queries Gemma,
        and saves blocking/safety result to the cache database.
        """
        domain = domain.lower().rstrip(".")
        if not force:
            cached = self.db.get_cached_ai_inspection(domain)
            if cached:
                print(f"[+] Loaded fresh AI inspection from cache database for {domain}")
                return cached

        # Execute live inspection
        result = self.inspector.inspect(domain)
        # Store blocking info & inspection in cache database
        self.db.save_ai_inspection(domain, result)
        print(f"[+] AI inspection stored in cache database. Verdict: {result.verdict} (Score: {result.score}/100)")
        return result

    def assess_domain(self, domain: str) -> RiskAssessment:
        """
        Evaluate domain using transparent rule-based weighted scoring.
        Distinguishes confirmed threat-feed matches from heuristic suspicion
        and integrates cached AI website inspections.
        Runs locally in microseconds without network overhead.
        """
        user_wl = self.db.get_custom_whitelist()
        is_wl = is_domain_whitelisted(domain, user_wl)
        feed_match = None
        ai_cache = None
        if not is_wl:
            feed_match = self.db.match_domain(domain)
            ai_cache = self.db.get_cached_ai_inspection(domain)

        return evaluate_domain_risk(domain, feed_match=feed_match, is_whitelisted=is_wl, ai_cache=ai_cache)

    def check_domain(self, domain: str) -> RiskAssessment:
        """Alias for assess_domain for seamless backward compatibility."""
        return self.assess_domain(domain)

    def is_blocked(self, domain: str) -> bool:
        """Convenience boolean check (True only if action is Block / HIGH RISK)."""
        return self.check_domain(domain).is_blocked

    def log_security_event(self, client_ip: str, domain: str, query_type: str, assessment: RiskAssessment) -> None:
        """Record a Block or Caution security event in the audit table."""
        rules_summary = "; ".join(f"{r.rule_id}(+{r.points})" for r in assessment.triggered_rules)
        source = assessment.record.source if assessment.record else "HeuristicEngine"
        threat_type = assessment.record.threat_type if assessment.record else "suspicious_characteristics"
        self.db.log_audit(
            client_ip=client_ip,
            domain=domain,
            matched_domain=assessment.matched_domain or domain,
            query_type=query_type,
            source=source,
            threat_type=threat_type,
            score=assessment.score,
            risk_level=assessment.risk_level.value,
            action=assessment.action.value,
            rules=rules_summary,
        )

    def log_blocked_query(self, client_ip: str, domain: str, query_type: str, result: RiskAssessment) -> None:
        """Backward-compatibility wrapper."""
        self.log_security_event(client_ip, domain, query_type, result)

    def start_background_sync(self, interval_seconds: int = 7200, sync_on_startup: bool = True) -> None:
        """
        Launch background worker thread that syncs feeds periodically.
        interval_seconds: default 7200 (2 hours).
        """
        if self._worker_thread and self._worker_thread.is_alive():
            return

        def _worker_loop():
            if sync_on_startup:
                # If database has 0 threats, sync immediately; otherwise delay slightly
                stats = self.db.get_stats()
                if stats["total_threats"] == 0:
                    print("[*] Threat database empty. Starting initial feed sync...")
                    self.sync_all()
                else:
                    print(f"[*] Threat database active with {stats['total_threats']} loaded domains.")

            while not self._stop_event.wait(timeout=interval_seconds):
                print("[*] Running periodic threat intelligence feed update...")
                self.sync_all()

        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=_worker_loop, name="ThreatSyncWorker", daemon=True)
        self._worker_thread.start()

    def stop_background_sync(self) -> None:
        """Signal background worker to stop."""
        self._stop_event.set()

    def close(self) -> None:
        """Stop background worker and close database connections."""
        self.stop_background_sync()
        self.db.close()


# ---------------------------------------------------------------------------
# Default Configured Instance Helper
# ---------------------------------------------------------------------------

def create_default_manager(db_path: str = "threats.db") -> ThreatIntelligenceManager:
    """Create a ThreatIntelligenceManager pre-configured with PhishTank and OpenPhish."""
    manager = ThreatIntelligenceManager(db_path=db_path)
    # 1. PhishTank Bulk Feed
    manager.register_feed(PhishTankFeed())
    # 2. OpenPhish Community Feed
    manager.register_feed(OpenPhishFeed())
    return manager


# ---------------------------------------------------------------------------
# Command Line Interface
# ---------------------------------------------------------------------------

def cli_main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Odikyu DNS Threat Intelligence Manager CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db", default="threats.db", help="Path to SQLite threat database")

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # sync
    subparsers.add_parser("sync", help="Synchronize all threat feeds into the local database")

    # stats
    subparsers.add_parser("stats", help="Display local threat database statistics")

    # check
    check_p = subparsers.add_parser("check", help="Check whether a domain is flagged as malicious")
    check_p.add_argument("domain", help="Domain to check")

    # inspect
    ins_p = subparsers.add_parser("inspect", help="Run AI-powered website inspection with gemma-4-31b-it (screenshot + network request)")
    ins_p.add_argument("domain", help="Domain to inspect")
    ins_p.add_argument("--force", action="store_true", help="Force live inspection, bypassing cache")

    # add
    add_p = subparsers.add_parser("add", help="Add a domain manually to the local threat database")
    add_p.add_argument("domain", help="Domain to block")
    add_p.add_argument("--type", default="custom", help="Threat type (default: custom)")
    add_p.add_argument("--source", default="Manual", help="Source name (default: Manual)")
    add_p.add_argument("--details", default="Manually added block rule", help="Rule details")

    # remove
    rem_p = subparsers.add_parser("remove", help="Remove a domain from the local threat database")
    rem_p.add_argument("domain", help="Domain to unblock")

    # whitelist
    wl_p = subparsers.add_parser("whitelist", help="Manage whitelisted domains (never blocked)")
    wl_sub = wl_p.add_subparsers(dest="wl_action", help="Whitelist action")
    wl_add = wl_sub.add_parser("add", help="Add domain to whitelist")
    wl_add.add_argument("domain", help="Domain to whitelist")
    wl_add.add_argument("--reason", default="User whitelist", help="Reason for whitelisting")
    wl_rem = wl_sub.add_parser("remove", help="Remove domain from whitelist")
    wl_rem.add_argument("domain", help="Domain to remove from whitelist")
    wl_sub.add_parser("list", help="List all whitelisted domains")

    # logs
    log_p = subparsers.add_parser("logs", help="View recent blocked DNS query audit logs")
    log_p.add_argument("-n", "--limit", type=int, default=20, help="Number of records to show")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    manager = create_default_manager(db_path=args.db)

    if args.command == "sync":
        print(f"[*] Synchronizing feeds into {args.db} ...")
        res = manager.sync_all()
        print("[+] Sync complete:")
        for feed, count in res.items():
            print(f"    - {feed}: {count} domains imported")

    elif args.command == "stats":
        stats = manager.db.get_stats()
        print("\n" + "=" * 60)
        print("  ODIKYU DNS - THREAT INTELLIGENCE DATABASE STATS")
        print("=" * 60)
        print(f"  Database Path         : {os.path.abspath(args.db)}")
        print(f"  Total Malicious Domains: {stats['total_threats']:,}")
        print(f"  Total Blocked Requests: {stats['total_blocked_queries']:,}")
        print("\n  Domains by Feed Source:")
        for src, cnt in stats["sources"].items():
            print(f"    * {src:<20}: {cnt:,}")
        print("\n  Domains by Threat Type:")
        for tt, cnt in stats["threat_types"].items():
            print(f"    * {tt:<20}: {cnt:,}")
        print("=" * 60 + "\n")

    elif args.command == "check":
        res = manager.check_domain(args.domain)
        print("\n" + "=" * 65)
        print(f"  RISK ASSESSMENT REPORT: {res.domain}")
        print("=" * 65)
        print(f"  Risk Level  : {res.risk_level.value}")
        print(f"  Action      : {res.action.value}")
        print(f"  Risk Score  : {res.score} / 100")
        print(f"  Assessment  : {res.summary}")

        if res.record:
            print(f"  Feed Source : {res.record.source} ({res.record.threat_type})")
            if res.record.details:
                print(f"  Feed Details: {res.record.details}")

        if res.triggered_rules:
            print("\n  Triggered Rules (Rule-Based Weighted Scoring):")
            for r in res.triggered_rules:
                pts = f"+{r.points}" if r.points > 0 else "0"
                print(f"    * [{r.rule_id:<24}] ({pts:>4} pts) [{r.category:<11}]: {r.description}")

        if res.risk_level == RiskLevel.LOW:
            print("\n  Note: No known threat detected. This does not guarantee that the domain is safe.")
        print("=" * 65 + "\n")

    elif args.command == "inspect":
        res = manager.inspect_website(args.domain, force=args.force)
        print("\n" + "=" * 68)
        print(f"  AI WEBSITE INSPECTION REPORT: {res.domain}")
        print(f"  Model Engine: {res.model_name}")
        print("=" * 68)
        print(f"  Verdict          : {res.verdict}")
        print(f"  Risk Level       : {res.risk_level}")
        print(f"  AI Safety Score  : {res.score} / 100")
        print(f"  Is Safe          : {res.is_safe}")
        if res.impersonated_brand:
            print(f"  Impersonated Brand: {res.impersonated_brand}")
        print(f"  Summary          : {res.summary}")

        if res.visual_indicators:
            print("\n  Visual Indicators (Screenshot Analysis):")
            for v in res.visual_indicators:
                print(f"    * {v}")

        if res.network_indicators:
            print("\n  Network Indicators (HTTP / TLS Telemetry):")
            for n in res.network_indicators:
                print(f"    * {n}")

        if res.screenshot_path:
            print(f"\n  Screenshot Cached: {res.screenshot_path}")

        if res.verdict == "Block":
            print("\n  [ACTION] Domain registered in threat blocklist and stored in cache database.")
        print("=" * 68 + "\n")

    elif args.command == "add":
        manager.db.upsert_threat(args.domain, args.source, args.type, args.details)
        print(f"[+] Domain '{args.domain}' added to threat database under source '{args.source}'.")

    elif args.command == "remove":
        ok = manager.db.delete_threat(args.domain)
        if ok:
            print(f"[+] Domain '{args.domain}' removed from threat database.")
        else:
            print(f"[-] Domain '{args.domain}' was not found in database.")

    elif args.command == "whitelist":
        if args.wl_action == "add":
            manager.db.add_to_whitelist(args.domain, args.reason)
            print(f"[+] Domain '{args.domain}' added to whitelist.")
        elif args.wl_action == "remove":
            ok = manager.db.remove_from_whitelist(args.domain)
            if ok:
                print(f"[+] Domain '{args.domain}' removed from whitelist.")
            else:
                print(f"[-] Domain '{args.domain}' was not found in custom whitelist.")
        elif args.wl_action == "list":
            custom_wl = manager.db.get_custom_whitelist()
            print("\n=== System Whitelist (Default) ===")
            print(", ".join(sorted(DEFAULT_WHITELIST)))
            print(f"\n=== User Whitelist ({len(custom_wl)}) ===")
            print(", ".join(sorted(custom_wl)) or "(none)")
            print()
        else:
            wl_p.print_help()

    elif args.command == "logs":
        logs = manager.db.get_recent_audit_logs(limit=args.limit)
        print(f"\n=== Security Query Audit Log ({len(logs)}) ===")
        for log in logs:
            score_info = f"Score: {log.get('score', 0)} ({log.get('risk_level', '')})" if log.get('risk_level') else f"[{log['source']} / {log['threat_type']}]"
            action_info = f"Action: {log.get('action', 'Block')}"
            print(f"[{log['timestamp']}] {log['client_ip']} -> {log['domain']} ({log['query_type']}) | {action_info} | {score_info}")
            if log.get('rules'):
                print(f"    Rules: {log['rules']}")
        print()


if __name__ == "__main__":
    cli_main()
