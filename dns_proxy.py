"""
Odikyu DNS Shield - DNS Proxy Server
====================================
Hosted at dns.odikyu.tech.
Listens on UDP port 53, forwards legitimate queries to an upstream
DNS-over-HTTPS (DoH, RFC 8484) server (default Cloudflare 1.1.1.1),
and evaluates every requested domain against an ultra-fast local SQLite
threat database with Gemma AI website inspection.

Key Architecture:
- Zero Per-Query Network Overhead: Threat evaluation runs locally in microseconds (< 0.1ms).
- Rule-Based Weighted Scoring: Distinguishes confirmed malicious threats from heuristic suspicion.
- Automated Gemma AI Inspection: Suspicious & unconfirmed domains are inspected asynchronously
  by Gemma-4-31b-it with network telemetry and visual screenshots, caching safety scores (1-100).
- HTTP Block / Warning Page: Intercepted malicious domains resolve to the server IP and render
  an informative, branded warning page with threat indicators, risk score, and safety advice.
- Threat Intelligence Sync: Background worker keeps PhishTank and OpenPhish feeds up-to-date.
"""

from __future__ import annotations

import base64
import os
import queue
import socket
import ssl
import struct
import threading
import time
import urllib.error
import urllib.request

import block_page_server
import config
from threat_manager import (
    CheckResult,
    RiskAction,
    RiskAssessment,
    RiskLevel,
    ScoredRule,
    ThreatDatabase,
    ThreatIntelligenceManager,
    ThreatRecord,
    create_default_manager,
)

# ---------------------------------------------------------------------------
# Configuration (from config.py / .env)
# ---------------------------------------------------------------------------

LISTEN_IP = config.DNS_LISTEN_IP
LISTEN_PORT = config.DNS_PORT
DOH_SERVER = config.DOH_SERVER
BLOCKED_IP = config.BLOCK_PAGE_IP
TIMEOUT = 5  # Upstream timeout in seconds

# ---------------------------------------------------------------------------
# TLS Setup for DoH Upstream
# ---------------------------------------------------------------------------

def _der_to_pem(der: bytes) -> str:
    """Convert a DER-encoded certificate to PEM text."""
    b64 = base64.b64encode(der).decode("ascii")
    lines = "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
    return f"-----BEGIN CERTIFICATE-----\n{lines}\n-----END CERTIFICATE-----\n"


def _make_ssl_context() -> ssl.SSLContext:
    """Build a verified SSL context for the DoH HTTPS connection."""
    context = ssl.create_default_context()
    try:
        import certifi
        context.load_verify_locations(certifi.where())
    except ImportError:
        try:
            cadata = ""
            for store in ("CA", "ROOT"):
                for cert, enc, _trust in ssl.enum_certificates(store):
                    if enc == "x509_asn":
                        cadata += _der_to_pem(cert)
            if cadata:
                context.load_verify_locations(cadata=cadata)
        except OSError:
            pass
    return context


SSL_CONTEXT = _make_ssl_context()

# ---------------------------------------------------------------------------
# Threat Intelligence Manager & AI Inspection Queue
# ---------------------------------------------------------------------------

THREAT_MANAGER = create_default_manager(db_path=config.THREAT_DB_PATH)


class BackgroundAIInspectionQueue:
    """
    Asynchronous worker queue for Gemma AI website inspections.
    Enables deep multimodal inspection of suspicious domains without
    introducing latency into real-time DNS resolution.
    """

    def __init__(self, manager: ThreatIntelligenceManager):
        self.manager = manager
        self.queue: queue.Queue[str] = queue.Queue(maxsize=1000)
        self.pending_domains: set[str] = set()
        self.lock = threading.Lock()
        self.worker_thread: threading.Thread | None = None
        self.running = False

    def enqueue(self, domain: str) -> bool:
        domain = domain.lower().rstrip(".")
        with self.lock:
            if domain in self.pending_domains:
                return False
            # Check if recently cached
            cached = self.manager.db.get_cached_ai_inspection(domain)
            if cached:
                return False
            self.pending_domains.add(domain)

        try:
            self.queue.put_nowait(domain)
            return True
        except queue.Full:
            with self.lock:
                self.pending_domains.discard(domain)
            return False

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True, name="AIInspectorWorker")
        self.worker_thread.start()

    def stop(self) -> None:
        self.running = False

    def _worker_loop(self) -> None:
        while self.running:
            try:
                domain = self.queue.get(timeout=2.0)
            except queue.Empty:
                continue

            try:
                print(f"[*] [AI-Worker] Inspecting suspicious domain '{domain}' with {config.GEMMA_MODEL_NAME}...")
                result = self.manager.inspect_website(domain, force=False)
                print(f"[+] [AI-Worker] Inspection complete for '{domain}': Verdict={result.verdict}, Score={result.score}/100")
            except Exception as exc:
                print(f"[!] [AI-Worker] Failed inspecting '{domain}': {exc}")
            finally:
                with self.lock:
                    self.pending_domains.discard(domain)
                self.queue.task_done()


AI_QUEUE = BackgroundAIInspectionQueue(THREAT_MANAGER)


def check_domain(domain: str) -> RiskAssessment:
    """Fast local risk assessment (< 0.1ms)."""
    return THREAT_MANAGER.check_domain(domain)


def is_blocked(domain: str) -> bool:
    """Backward-compatible boolean check."""
    return THREAT_MANAGER.is_blocked(domain)


# ---------------------------------------------------------------------------
# DNS Packet Parsing Helpers
# ---------------------------------------------------------------------------

def parse_query_name(data: bytes, offset: int) -> tuple[str, int]:
    """Read a DNS-encoded name starting at offset -> (name, new_offset)."""
    labels = []
    while True:
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if (length & 0xC0) == 0xC0:
            offset += 2
            break
        offset += 1
        labels.append(data[offset:offset + length].decode("ascii", errors="ignore"))
        offset += length
    return ".".join(labels), offset


def build_name(name: str) -> bytes:
    """Encode domain name into DNS wire format."""
    out = b""
    for label in name.rstrip(".").split("."):
        out += bytes([len(label)]) + label.encode("ascii")
    return out + b"\x00"


# ---------------------------------------------------------------------------
# Blocked Response Builder
# ---------------------------------------------------------------------------

def build_blocked_response(query: bytes, resolved_ip: str) -> bytes:
    """
    Build DNS response pointing to the Block Page IP (default 127.0.0.1 or server IP)
    so the user's browser accesses the Odikyu Warning Page.
    """
    tid = query[:2]
    flags = struct.unpack("!H", query[2:4])[0]

    # QR=1 (response), RA=1 (recursion available)
    resp_flags = (flags & 0x7900) | 0x8000 | 0x0080

    domain, q_end = parse_query_name(query, 12)
    question = query[12:q_end + 4]
    qtype = struct.unpack("!H", query[q_end + 2:q_end + 4])[0]

    # Type A record -> Answer with BLOCKED_IP (Block Page server)
    if qtype == 1:
        try:
            rdata = socket.inet_aton(resolved_ip)
        except OSError:
            rdata = socket.inet_aton("127.0.0.1")
        answer = build_name(domain) + struct.pack("!HHIH", 1, 1, 10, 4) + rdata
        header = tid + struct.pack("!HHHHH", resp_flags, 1, 1, 0, 0) + question
        return header + answer

    # Type AAAA record -> ::
    if qtype == 28:
        answer = build_name(domain) + struct.pack("!HHIH", 28, 1, 10, 16) + b"\x00" * 16
        header = tid + struct.pack("!HHHHH", resp_flags, 1, 1, 0, 0) + question
        return header + answer

    header = tid + struct.pack("!HHHHH", resp_flags, 1, 0, 0, 0) + question
    return header


# ---------------------------------------------------------------------------
# Forwarding to Upstream (DNS over HTTPS, RFC 8484)
# ---------------------------------------------------------------------------

def forward_to_upstream(query: bytes) -> bytes | None:
    """Forward raw DNS query to upstream DoH server."""
    request = urllib.request.Request(
        DOH_SERVER,
        data=query,
        method="POST",
        headers={
            "Content-Type": "application/dns-message",
            "Accept": "application/dns-message",
            "User-Agent": "odikyu-dns-shield/2.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT, context=SSL_CONTEXT) as resp:
            if resp.status != 200:
                print(f"[!] DoH upstream returned HTTP {resp.status}")
                return None
            return resp.read()
    except urllib.error.HTTPError as exc:
        print(f"[!] DoH HTTP error: {exc.code} {exc.reason}")
        return None
    except (urllib.error.URLError, socket.timeout, OSError) as exc:
        print(f"[!] DoH request failed: {exc}")
        return None


# ---------------------------------------------------------------------------
# Alert Logging & Display
# ---------------------------------------------------------------------------

def show_security_alert(client_ip: str, domain: str, query_type: str, assessment: RiskAssessment) -> None:
    """Print structured security alert in console."""
    print("=" * 65)
    if assessment.action == RiskAction.BLOCK:
        print("  [!] HIGH RISK: MALICIOUS SITE BLOCKED")
        print(f"  Action          : {assessment.action.value} -> Redirected to Block Page ({BLOCKED_IP})")
    elif assessment.action == RiskAction.CAUTION:
        print("  [?] SUSPICIOUS: CAUTION ADVISED")
        print(f"  Action          : {assessment.action.value}")
    else:
        print("  [*] LOW RISK: ALLOWED")
        print(f"  Action          : {assessment.action.value}")

    print(f"  Requested Domain: {domain}")
    print(f"  Client IP       : {client_ip}")
    print(f"  Query Type      : {query_type}")
    print(f"  Risk Score      : {assessment.score} / 100 ({assessment.risk_level.value})")
    print(f"  Assessment      : {assessment.summary}")

    if assessment.record:
        print(f"  Threat Source   : {assessment.record.source} ({assessment.record.threat_type})")
        if assessment.record.details:
            print(f"  Feed Details    : {assessment.record.details}")

    if assessment.triggered_rules:
        print("  Triggered Rules (Rule-Based Weighted Scoring):")
        for r in assessment.triggered_rules:
            pts = f"+{r.points}" if r.points > 0 else "0"
            print(f"    * [{r.rule_id}] ({pts} pts): {r.description}")
    print("=" * 65)


# ---------------------------------------------------------------------------
# Per-Request Handler
# ---------------------------------------------------------------------------

def handle_request(data: bytes, client_addr):
    """Process incoming DNS query."""
    try:
        domain, q_end = parse_query_name(data, 12)
        qtype_num = struct.unpack("!H", data[q_end + 2:q_end + 4])[0]
        qtype = {1: "A", 28: "AAAA", 5: "CNAME", 15: "MX", 16: "TXT"}.get(qtype_num, f"TYPE{qtype_num}")
    except (IndexError, struct.error):
        return

    # Fast Rule-Based Risk Assessment (< 0.1ms)
    assessment = check_domain(domain)

    if assessment.action == RiskAction.BLOCK:
        # HIGH RISK: Block & Sinkhole to Block Page
        show_security_alert(client_addr[0], domain, qtype, assessment)
        THREAT_MANAGER.log_security_event(client_addr[0], domain, qtype, assessment)
        response = build_blocked_response(data, BLOCKED_IP)

    elif assessment.action == RiskAction.CAUTION:
        # SUSPICIOUS: Caution advised
        show_security_alert(client_addr[0], domain, qtype, assessment)
        THREAT_MANAGER.log_security_event(client_addr[0], domain, qtype, assessment)

        # Trigger background Gemma AI inspection if not yet inspected
        if config.AUTO_INSPECT_SUSPICIOUS and config.AI_INSPECTION_ENABLED:
            if AI_QUEUE.enqueue(domain):
                print(f"[*] Queued '{domain}' for Gemma-4-31b-it multimodal inspection.")

        if config.BLOCK_SUSPICIOUS:
            print(f"[!] BLOCK_SUSPICIOUS active: Redirecting suspicious '{domain}' to Warning Page ({BLOCKED_IP})")
            response = build_blocked_response(data, BLOCKED_IP)
        else:
            response = forward_to_upstream(data)
            if response is None:
                return

    else:
        # LOW RISK: Forward to upstream DoH
        print(f"[->] Forwarding {domain} ({qtype}) from {client_addr[0]} [LOW RISK]")
        response = forward_to_upstream(data)
        if response is None:
            return

    try:
        server.sendto(response, client_addr)
    except OSError as exc:
        print(f"[!] Failed to send response to {client_addr}: {exc}")


# ---------------------------------------------------------------------------
# Main Server Loop
# ---------------------------------------------------------------------------

def main():
    global server
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        server.bind((LISTEN_IP, LISTEN_PORT))
    except OSError as exc:
        print(f"[!] Failed to bind UDP {LISTEN_IP}:{LISTEN_PORT}: {exc}")
        print("[!] Note: Port 53 requires administrator / root privileges.")
        return

    # 1. Start Threat Intelligence background feed sync
    THREAT_MANAGER.start_background_sync(interval_seconds=config.SYNC_INTERVAL_SECONDS, sync_on_startup=False)

    # 2. Start Gemma AI website inspection background queue
    if config.AI_INSPECTION_ENABLED:
        AI_QUEUE.start()

    # 3. Start HTTP Warning & Block Page Server in background
    try:
        _, http_server, actual_http_port = block_page_server.start_block_page_server_thread(
            host="0.0.0.0",
            port=config.BLOCK_PAGE_PORT,
            tm=THREAT_MANAGER,
        )
    except Exception as exc:
        print(f"[!] Warning: HTTP Warning Server failed to start: {exc}")
        http_server = None
        actual_http_port = None

    stats = THREAT_MANAGER.db.get_stats()
    print("=" * 65)
    print("  🛡️  ODIKYU DNS SHIELD - THREAT PROTECTION PROXY")
    print("=" * 65)
    print(f"  Server Hostname    : {config.SERVER_HOSTNAME}")
    print(f"  DNS Listening      : UDP {LISTEN_IP}:{LISTEN_PORT}")
    print(f"  Block Page Server  : HTTP 0.0.0.0:{actual_http_port} (Sinkhole IP: {BLOCKED_IP})")
    print(f"  Upstream DoH       : {DOH_SERVER}")
    print(f"  AI Inspection Model: {config.GEMMA_MODEL_NAME} (Google AI Studio)")
    print(f"  Loaded Threats     : {stats['total_threats']:,} domains in local DB")
    print(f"  Active Threat Feeds: {', '.join(THREAT_MANAGER.feeds.keys())}")
    print(f"  Block Suspicious   : {config.BLOCK_SUSPICIOUS}")
    print(f"  Auto AI Inspection : {config.AUTO_INSPECT_SUSPICIOUS}")
    print(f"  Management UI      : http://{config.SERVER_HOSTNAME}:{actual_http_port}/")
    print("=" * 65)
    print("[*] Ready for queries. Press Ctrl+C to terminate.\n")

    while True:
        try:
            data, client_addr = server.recvfrom(4096)
        except KeyboardInterrupt:
            print("\n[*] Terminating Odikyu DNS Shield...")
            THREAT_MANAGER.stop_background_sync()
            AI_QUEUE.stop()
            if http_server:
                http_server.shutdown()
            server.close()
            break

        # Handle each query concurrently
        threading.Thread(target=handle_request, args=(data, client_addr), daemon=True).start()


if __name__ == "__main__":
    main()
