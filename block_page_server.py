"""
Odikyu DNS Shield - HTTP Warning & Block Page Server
===================================================
Hosted at dns.odikyu.tech. When the DNS proxy blocks a malicious or suspicious
domain, it answers with the Block Page IP (e.g. 127.0.0.1 or public IP).
When the user's browser attempts to connect to the site via HTTP, this server
intercepts the request, inspects the requested domain (via Host header),
queries the local threat intelligence database & Gemma AI inspection cache,
and renders an informative, high-tech security warning page.

Endpoints:
- Any sinkholed domain (e.g. Host: phishing.xyz) -> Security Alert / Warning Page
- dns.odikyu.tech / localhost / /admin           -> Odikyu DNS Shield Dashboard
- /api/check?domain=<name>                      -> JSON threat lookup
- /api/inspect?domain=<name>                    -> On-demand Gemma AI inspection
- /api/stats                                    -> Threat database statistics
- /healthz                                      -> Healthcheck
"""

from __future__ import annotations

import html
import http.server
import json
import os
import socketserver
import threading
import urllib.parse
from typing import Any

import config
from threat_manager import (
    RiskAction,
    RiskAssessment,
    RiskLevel,
    ThreatIntelligenceManager,
    create_default_manager,
)


# Global threat manager instance
_THREAT_MANAGER: ThreatIntelligenceManager | None = None


def get_threat_manager() -> ThreatIntelligenceManager:
    global _THREAT_MANAGER
    if _THREAT_MANAGER is None:
        _THREAT_MANAGER = create_default_manager(db_path=config.THREAT_DB_PATH)
    return _THREAT_MANAGER


def set_threat_manager(tm: ThreatIntelligenceManager) -> None:
    global _THREAT_MANAGER
    _THREAT_MANAGER = tm


# ---------------------------------------------------------------------------
# HTML Templates
# ---------------------------------------------------------------------------

WARNING_PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Security Alert: Access Blocked | Odikyu DNS Shield</title>
    <style>
        :root {{
            --bg-primary: #0a0e17;
            --bg-card: #121826;
            --bg-card-border: #1f293d;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --danger-red: #ef4444;
            --danger-bg: rgba(239, 68, 68, 0.12);
            --danger-border: rgba(239, 68, 68, 0.4);
            --warn-amber: #f59e0b;
            --warn-bg: rgba(245, 158, 11, 0.12);
            --accent-cyan: #06b6d4;
            --accent-glow: rgba(6, 182, 212, 0.2);
            --badge-bg: #1e293b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            background: radial-gradient(circle at 50% 10%, #151e32 0%, var(--bg-primary) 100%);
            color: var(--text-main);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 24px;
        }}
        .container {{
            max-width: 760px;
            width: 100%;
            background: var(--bg-card);
            border: 1px solid var(--bg-card-border);
            border-radius: 16px;
            box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.6), 0 0 40px {glow_color};
            overflow: hidden;
            animation: fadeIn 0.3s ease-out;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(12px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .header {{
            background: {header_bg};
            border-bottom: 1px solid {header_border};
            padding: 24px 32px;
            display: flex;
            align-items: center;
            gap: 18px;
        }}
        .icon-shield {{
            width: 48px;
            height: 48px;
            border-radius: 12px;
            background: {badge_icon_bg};
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 26px;
            flex-shrink: 0;
        }}
        .header-title h1 {{
            font-size: 20px;
            font-weight: 700;
            color: {accent_color};
            letter-spacing: -0.3px;
        }}
        .header-title p {{
            font-size: 13px;
            color: var(--text-muted);
            margin-top: 2px;
        }}
        .content {{
            padding: 32px;
        }}
        .domain-box {{
            background: #0d131f;
            border: 1px solid #1e293b;
            border-radius: 10px;
            padding: 16px 20px;
            margin-bottom: 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .domain-name {{
            font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
            font-size: 18px;
            color: #ffffff;
            font-weight: 600;
            word-break: break-all;
        }}
        .risk-badge {{
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.5px;
            text-transform: uppercase;
            background: {badge_bg};
            color: {accent_color};
            border: 1px solid {badge_border};
        }}
        .score-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .stat-card {{
            background: #0d131f;
            border: 1px solid #1a2233;
            border-radius: 10px;
            padding: 14px 16px;
        }}
        .stat-label {{
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 6px;
        }}
        .stat-value {{
            font-size: 18px;
            font-weight: 700;
            color: #ffffff;
        }}
        .summary-card {{
            background: {alert_bg};
            border-left: 4px solid {accent_color};
            border-radius: 8px;
            padding: 16px 20px;
            margin-bottom: 24px;
            font-size: 14px;
            line-height: 1.6;
        }}
        .section-title {{
            font-size: 13px;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-muted);
            margin-bottom: 12px;
        }}
        .indicators-list {{
            list-style: none;
            margin-bottom: 24px;
        }}
        .indicators-list li {{
            padding: 10px 14px;
            background: #0d131f;
            border-radius: 8px;
            margin-bottom: 8px;
            font-size: 13px;
            display: flex;
            align-items: flex-start;
            gap: 10px;
            border: 1px solid #182236;
        }}
        .bullet {{
            color: {accent_color};
            font-size: 16px;
            line-height: 1;
        }}
        .advice-box {{
            background: #0b111c;
            border: 1px solid #1e293b;
            border-radius: 10px;
            padding: 18px 20px;
            margin-bottom: 24px;
            font-size: 13px;
            color: #cbd5e1;
            line-height: 1.6;
        }}
        .advice-box strong {{
            color: #ffffff;
        }}
        .footer {{
            padding: 18px 32px;
            background: #0b101a;
            border-top: 1px solid #182234;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 12px;
            color: var(--text-muted);
            flex-wrap: wrap;
            gap: 10px;
        }}
        .footer a {{
            color: var(--accent-cyan);
            text-decoration: none;
        }}
        .footer a:hover {{
            text-decoration: underline;
        }}
        details {{
            margin-top: 12px;
        }}
        details summary {{
            cursor: pointer;
            color: var(--accent-cyan);
            font-size: 12px;
            outline: none;
            user-select: none;
        }}
        .details-pre {{
            margin-top: 10px;
            padding: 12px;
            background: #060a12;
            border-radius: 6px;
            font-family: monospace;
            font-size: 11px;
            overflow-x: auto;
            color: #94a3b8;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="icon-shield">{icon}</div>
            <div class="header-title">
                <h1>{headline}</h1>
                <p>Odikyu DNS Shield &bull; Automated Threat Defense &bull; dns.odikyu.tech</p>
            </div>
        </div>

        <div class="content">
            <div class="domain-box">
                <div class="domain-name">{domain}</div>
                <div class="risk-badge">{risk_level} &bull; SCORE {score}/100</div>
            </div>

            <div class="score-row">
                <div class="stat-card">
                    <div class="stat-label">Action Taken</div>
                    <div class="stat-value" style="color: {accent_color};">{action}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Detection Source</div>
                    <div class="stat-value">{threat_source}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Inspection Engine</div>
                    <div class="stat-value">{engine_name}</div>
                </div>
            </div>

            <div class="summary-card">
                <strong>Threat Summary:</strong> {summary}
            </div>

            {indicators_html}

            <div class="advice-box">
                <strong>Why was this site blocked?</strong><br>
                Odikyu DNS Shield detected evidence consistent with credential harvesting, brand phishing, or malware distribution on this domain.
                Entering passwords, personal identifiers, or credit card numbers on this website puts your accounts and devices at serious risk.
            </div>

            <details>
                <summary>View Technical Diagnostic Details</summary>
                <div class="details-pre">
Client IP: {client_ip}
Timestamp: {timestamp}
Protected By: Odikyu DNS Shield (dns.odikyu.tech)
Upstream DNS: RFC 8484 DNS-over-HTTPS (Cloudflare 1.1.1.1)
AI Multimodal Engine: Gemma-4-31b-it Vision & Telemetry Inspector
Diagnostic Data:
{technical_details}
                </div>
            </details>
        </div>

        <div class="footer">
            <span>Server: <code>dns.odikyu.tech</code></span>
            <span>Powered by <strong>Odikyu DNS Shield & Gemma AI</strong></span>
        </div>
    </div>
</body>
</html>
"""

DASHBOARD_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Odikyu DNS Shield | Threat Intelligence & Proxy Control</title>
    <style>
        :root {{
            --bg-dark: #0a0e17;
            --bg-panel: #111726;
            --border-color: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-cyan: #06b6d4;
            --accent-blue: #3b82f6;
            --success-green: #10b981;
            --danger-red: #ef4444;
            --warn-amber: #f59e0b;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #080c14;
            color: var(--text-primary);
            padding: 30px 20px;
            min-height: 100vh;
        }}
        .wrap {{
            max-width: 1100px;
            margin: 0 auto;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 24px;
            border-bottom: 1px solid var(--border-color);
            margin-bottom: 28px;
            flex-wrap: wrap;
            gap: 16px;
        }}
        .header h1 {{
            font-size: 24px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        .status-pill {{
            background: rgba(16, 185, 129, 0.15);
            color: var(--success-green);
            border: 1px solid rgba(16, 185, 129, 0.3);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .status-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--success-green);
            box-shadow: 0 0 8px var(--success-green);
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 18px;
            margin-bottom: 28px;
        }}
        .stat-box {{
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }}
        .stat-box .title {{
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }}
        .stat-box .num {{
            font-size: 28px;
            font-weight: 700;
            color: #ffffff;
        }}
        .card {{
            background: var(--bg-panel);
            border: 1px solid var(--border-color);
            border-radius: 14px;
            padding: 24px;
            margin-bottom: 28px;
        }}
        .card h2 {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 16px;
            color: #ffffff;
        }}
        .input-group {{
            display: flex;
            gap: 12px;
            margin-bottom: 16px;
        }}
        .input-group input {{
            flex: 1;
            padding: 12px 16px;
            background: #0a0e17;
            border: 1px solid #273549;
            border-radius: 8px;
            color: #fff;
            font-size: 14px;
            outline: none;
        }}
        .input-group input:focus {{
            border-color: var(--accent-cyan);
        }}
        .btn {{
            padding: 12px 20px;
            background: var(--accent-cyan);
            color: #05131f;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .btn:hover {{
            background: #22d3ee;
        }}
        .btn-inspect {{
            background: #8b5cf6;
            color: #ffffff;
        }}
        .btn-inspect:hover {{
            background: #a78bfa;
        }}
        #checkResult {{
            margin-top: 16px;
            padding: 16px;
            border-radius: 8px;
            background: #090e17;
            border: 1px solid #1f2c3f;
            font-family: monospace;
            font-size: 13px;
            white-space: pre-wrap;
            display: none;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            margin-top: 12px;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #1a2333;
        }}
        th {{
            color: var(--text-secondary);
            font-weight: 600;
            text-transform: uppercase;
            font-size: 11px;
            letter-spacing: 0.5px;
        }}
        tr:hover {{
            background: rgba(255, 255, 255, 0.02);
        }}
        .badge {{
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge-block {{
            background: rgba(239, 68, 68, 0.2);
            color: var(--danger-red);
        }}
        .badge-caution {{
            background: rgba(245, 158, 11, 0.2);
            color: var(--warn-amber);
        }}
        .badge-allow {{
            background: rgba(16, 185, 129, 0.2);
            color: var(--success-green);
        }}
        .footer {{
            text-align: center;
            font-size: 12px;
            color: var(--text-secondary);
            margin-top: 40px;
        }}
    </style>
</head>
<body>
    <div class="wrap">
        <div class="header">
            <div>
                <h1>🛡️ Odikyu DNS Shield</h1>
                <p style="color: var(--text-secondary); font-size: 14px; margin-top: 4px;">
                    Enterprise Phishing & Malware Protection &bull; Server Host: <code>{server_host}</code>
                </p>
            </div>
            <div class="status-pill">
                <span class="status-dot"></span>
                DNS Filtering Active & Protecting
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-box">
                <div class="title">Known Threat Domains</div>
                <div class="num" style="color: var(--accent-cyan);">{total_threats:,}</div>
            </div>
            <div class="stat-box">
                <div class="title">Blocked Queries</div>
                <div class="num" style="color: var(--danger-red);">{total_blocked:,}</div>
            </div>
            <div class="stat-box">
                <div class="title">AI Inspection Engine</div>
                <div class="num" style="font-size: 20px; color: #a78bfa;">{gemma_model}</div>
            </div>
            <div class="stat-box">
                <div class="title">Upstream Resolver</div>
                <div class="num" style="font-size: 18px; color: #60a5fa;">RFC 8484 DoH</div>
            </div>
        </div>

        <div class="card">
            <h2>🔍 Threat Intelligence & AI Inspection Console</h2>
            <p style="color: var(--text-secondary); font-size: 13px; margin-bottom: 14px;">
                Test any domain against the local threat database or trigger a multimodal visual and network telemetry inspection using Gemma AI.
            </p>
            <div class="input-group">
                <input type="text" id="domainInput" placeholder="Enter domain (e.g. secure-paypal-verify.xyz)" />
                <button class="btn" onclick="checkDomain()">Instant DB Check</button>
                <button class="btn btn-inspect" onclick="inspectWithAI()">Gemma AI Inspect</button>
            </div>
            <div id="checkResult"></div>
        </div>

        <div class="card">
            <h2>📋 Recent Security Audit Events</h2>
            <table>
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Client IP</th>
                        <th>Requested Domain</th>
                        <th>Action</th>
                        <th>Score</th>
                        <th>Source / Detection Reason</th>
                    </tr>
                </thead>
                <tbody>
                    {recent_audit_rows}
                </tbody>
            </table>
        </div>

        <div class="footer">
            Odikyu DNS Shield &bull; Hosted at <strong>dns.odikyu.tech</strong> &bull; Powered by PhishTank, OpenPhish & Gemma-4-31b-it
        </div>
    </div>

    <script>
        async function checkDomain() {{
            const d = document.getElementById("domainInput").value.trim();
            if (!d) return;
            const resEl = document.getElementById("checkResult");
            resEl.style.display = "block";
            resEl.textContent = "Checking local threat database...";
            try {{
                const r = await fetch(`/api/check?domain=${{encodeURIComponent(d)}}`);
                const data = await r.json();
                resEl.textContent = JSON.stringify(data, null, 2);
            }} catch (e) {{
                resEl.textContent = "Error: " + e;
            }}
        }}

        async function inspectWithAI() {{
            const d = document.getElementById("domainInput").value.trim();
            if (!d) return;
            const resEl = document.getElementById("checkResult");
            resEl.style.display = "block";
            resEl.textContent = "Capturing network telemetry, visual screenshot, and invoking Gemma-4-31b-it (this may take 15-30 seconds)...";
            try {{
                const r = await fetch(`/api/inspect?domain=${{encodeURIComponent(d)}}`);
                const data = await r.json();
                resEl.textContent = JSON.stringify(data, null, 2);
            }} catch (e) {{
                resEl.textContent = "Inspection failed: " + e;
            }}
        }}
    </script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Request Handler
# ---------------------------------------------------------------------------

class OdikyuBlockPageHandler(http.server.BaseHTTPRequestHandler):
    """
    HTTP Request Handler serving warning pages for blocked domains
    and the management dashboard on the host domain.
    """

    def log_message(self, format: str, *args: Any) -> None:
        """Compact access logger."""
        print(f"[HTTP] {self.address_string()} - {format % args}")

    def do_HEAD(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. API Endpoints
        if path == "/api/check":
            self._handle_api_check(query)
            return
        elif path == "/api/inspect":
            self._handle_api_inspect(query)
            return
        elif path == "/api/stats":
            self._handle_api_stats()
            return
        elif path == "/healthz":
            self._handle_healthz()
            return

        # 2. Host extraction
        host_header = self.headers.get("Host", "").lower().strip()
        requested_domain = host_header.split(":")[0] if host_header else ""

        # Check if visiting the control dashboard
        is_dashboard = (
            path in ("/admin", "/dashboard", "/status")
            or requested_domain in ("127.0.0.1", "localhost", config.SERVER_HOSTNAME.lower(), "dns.odikyu.tech")
        )

        if is_dashboard and path in ("/", "/admin", "/dashboard", "/status"):
            self._render_dashboard()
            return

        # Otherwise: render Warning Page for the intercepted blocked/suspicious domain
        self._render_warning_page(requested_domain or "Unknown Malicious Domain")

    def _send_json(self, status: int, data: dict) -> None:
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_healthz(self) -> None:
        self._send_json(200, {
            "status": "healthy",
            "server": config.SERVER_HOSTNAME,
            "service": "Odikyu DNS Shield",
            "version": "1.0",
        })

    def _handle_api_stats(self) -> None:
        tm = get_threat_manager()
        stats = tm.db.get_stats()
        stats["server_hostname"] = config.SERVER_HOSTNAME
        stats["gemma_model"] = config.GEMMA_MODEL_NAME
        self._send_json(200, stats)

    def _handle_api_check(self, query: dict[str, list[str]]) -> None:
        domain = query.get("domain", [""])[0].strip()
        if not domain:
            self._send_json(400, {"error": "Missing 'domain' query parameter"})
            return

        tm = get_threat_manager()
        assessment = tm.assess_domain(domain)
        cached_ai = tm.db.get_cached_ai_inspection(domain)

        data = {
            "domain": domain,
            "risk_level": assessment.risk_level.value,
            "action": assessment.action.value,
            "score": assessment.score,
            "summary": assessment.summary,
            "matched_domain": assessment.matched_domain,
            "threat_source": assessment.record.source if assessment.record else None,
            "threat_type": assessment.record.threat_type if assessment.record else None,
            "triggered_rules": [
                {"id": r.rule_id, "name": r.name, "points": r.points, "desc": r.description}
                for r in assessment.triggered_rules
            ],
            "ai_cached": cached_ai is not None,
        }
        if cached_ai:
            data["ai_details"] = {
                "verdict": cached_ai.verdict,
                "score": cached_ai.score,
                "impersonated_brand": cached_ai.impersonated_brand,
                "visual_indicators": cached_ai.visual_indicators,
                "network_indicators": cached_ai.network_indicators,
                "inspected_at": cached_ai.inspected_at,
            }
        self._send_json(200, data)

    def _handle_api_inspect(self, query: dict[str, list[str]]) -> None:
        domain = query.get("domain", [""])[0].strip()
        if not domain:
            self._send_json(400, {"error": "Missing 'domain' query parameter"})
            return

        force = query.get("force", ["false"])[0].lower() in ("1", "true", "yes")
        tm = get_threat_manager()
        try:
            result = tm.inspect_website(domain, force=force)
            data = {
                "domain": result.domain,
                "is_safe": result.is_safe,
                "score": result.score,
                "verdict": result.verdict,
                "risk_level": result.risk_level,
                "impersonated_brand": result.impersonated_brand,
                "summary": result.summary,
                "visual_indicators": result.visual_indicators,
                "network_indicators": result.network_indicators,
                "model_name": result.model_name,
                "inspected_at": result.inspected_at,
                "screenshot_captured": bool(result.screenshot_path),
            }
            self._send_json(200, data)
        except Exception as exc:
            self._send_json(500, {"error": str(exc), "domain": domain})

    def _render_dashboard(self) -> None:
        tm = get_threat_manager()
        stats = tm.db.get_stats()
        recent_logs = tm.db.get_recent_audit_logs(limit=15)

        rows = []
        for log in recent_logs:
            act = log.get("action", "")
            badge_cls = "badge-block" if act == "Block" else ("badge-caution" if act == "Caution" else "badge-allow")
            ts = log.get("timestamp", "")
            ip = html.escape(str(log.get("client_ip", "")))
            d = html.escape(str(log.get("domain", "")))
            score = log.get("score", 0)
            src = html.escape(str(log.get("source", "") or "HeuristicEngine"))
            rows.append(f"""
                <tr>
                    <td style="color: #94a3b8; font-family: monospace;">{ts}</td>
                    <td style="font-family: monospace;">{ip}</td>
                    <td style="font-weight: 600; color: #fff;">{d}</td>
                    <td><span class="badge {badge_cls}">{html.escape(act)}</span></td>
                    <td style="font-weight: 700;">{score}</td>
                    <td>{src}</td>
                </tr>
            """)

        recent_rows_html = "".join(rows) if rows else "<tr><td colspan='6' style='text-align: center; color: #94a3b8;'>No security events recorded yet.</td></tr>"

        page = DASHBOARD_TEMPLATE.format(
            server_host=html.escape(config.SERVER_HOSTNAME),
            total_threats=stats.get("total_threats", 0),
            total_blocked=stats.get("total_blocked_queries", 0),
            gemma_model=html.escape(config.GEMMA_MODEL_NAME),
            recent_audit_rows=recent_rows_html,
        )

        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _render_warning_page(self, domain: str) -> None:
        tm = get_threat_manager()
        assessment = tm.assess_domain(domain)
        cached_ai = tm.db.get_cached_ai_inspection(domain)

        is_high_risk = assessment.risk_level == RiskLevel.HIGH or assessment.score >= 75
        accent_color = "#ef4444" if is_high_risk else "#f59e0b"
        header_bg = "rgba(239, 68, 68, 0.15)" if is_high_risk else "rgba(245, 158, 11, 0.15)"
        header_border = "rgba(239, 68, 68, 0.3)" if is_high_risk else "rgba(245, 158, 11, 0.3)"
        alert_bg = "rgba(239, 68, 68, 0.08)" if is_high_risk else "rgba(245, 158, 11, 0.08)"
        badge_bg = "rgba(239, 68, 68, 0.2)" if is_high_risk else "rgba(245, 158, 11, 0.2)"
        badge_border = "rgba(239, 68, 68, 0.4)" if is_high_risk else "rgba(245, 158, 11, 0.4)"
        badge_icon_bg = "rgba(239, 68, 68, 0.2)" if is_high_risk else "rgba(245, 158, 11, 0.2)"
        glow_color = "rgba(239, 68, 68, 0.15)" if is_high_risk else "rgba(245, 158, 11, 0.15)"
        icon = "⛔" if is_high_risk else "⚠️"
        headline = "SECURITY THREAT BLOCKED" if is_high_risk else "SUSPICIOUS WEBSITE DETECTED"

        # Determine threat source and engine
        threat_source = "Unknown"
        engine_name = "Rule-Based Scoring"
        if assessment.record:
            threat_source = f"{assessment.record.source} ({assessment.record.threat_type})"
            engine_name = "Threat Intelligence Feed"
        elif cached_ai:
            threat_source = f"Gemma AI ({cached_ai.verdict})"
            engine_name = f"Multimodal AI ({cached_ai.model_name})"
        else:
            threat_source = "Heuristic Suspicion"
            engine_name = "Rule-Based Scoring Engine"

        # Build indicators list
        indicators = []
        for rule in assessment.triggered_rules:
            pts = f"+{rule.points} pts" if rule.points > 0 else ""
            indicators.append(f"<strong>[{rule.name}]</strong> {html.escape(rule.description)} <span style='color: var(--text-muted);'>{pts}</span>")

        if cached_ai:
            for v in cached_ai.visual_indicators:
                indicators.append(f"<strong>[Visual Indicator]</strong> {html.escape(v)}")
            for n in cached_ai.network_indicators:
                indicators.append(f"<strong>[Network Indicator]</strong> {html.escape(n)}")

        indicators_html = ""
        if indicators:
            items_str = "".join(f"<li><span class='bullet'>&bull;</span><div>{i}</div></li>" for i in indicators)
            indicators_html = f"""
                <div class="section-title">Detection Evidence & Triggered Security Rules</div>
                <ul class="indicators-list">{items_str}</ul>
            """

        tech_details = json.dumps({
            "requested_domain": domain,
            "risk_level": assessment.risk_level.value,
            "action": assessment.action.value,
            "score": assessment.score,
            "summary": assessment.summary,
            "matched_domain": assessment.matched_domain,
            "threat_record": {
                "source": assessment.record.source,
                "threat_type": assessment.record.threat_type,
                "details": assessment.record.details,
            } if assessment.record else None,
            "triggered_rules": [
                {"id": r.rule_id, "name": r.name, "points": r.points}
                for r in assessment.triggered_rules
            ],
            "ai_cache_found": cached_ai is not None,
        }, indent=2)

        import time
        page = WARNING_PAGE_TEMPLATE.format(
            headline=headline,
            icon=icon,
            domain=html.escape(domain),
            risk_level=assessment.risk_level.value,
            score=assessment.score,
            action=assessment.action.value,
            threat_source=html.escape(threat_source),
            engine_name=html.escape(engine_name),
            summary=html.escape(assessment.summary),
            indicators_html=indicators_html,
            client_ip=html.escape(self.address_string()),
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            technical_details=html.escape(tech_details),
            accent_color=accent_color,
            header_bg=header_bg,
            header_border=header_border,
            alert_bg=alert_bg,
            badge_bg=badge_bg,
            badge_border=badge_border,
            badge_icon_bg=badge_icon_bg,
            glow_color=glow_color,
        )

        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ---------------------------------------------------------------------------
# Threaded Server
# ---------------------------------------------------------------------------

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def run_block_page_server(
    host: str = "0.0.0.0",
    port: int | None = None,
    tm: ThreatIntelligenceManager | None = None,
) -> tuple[ThreadedHTTPServer, int]:
    """
    Start the Block Page HTTP server on the configured port.
    If port 80 fails (e.g. permission denied without root on Linux/Windows),
    automatically attempts fallback port (e.g. 8080).
    """
    if tm is not None:
        set_threat_manager(tm)

    preferred_port = port or config.BLOCK_PAGE_PORT
    alt_port = config.BLOCK_PAGE_ALT_PORT

    server = None
    actual_port = preferred_port
    try:
        server = ThreadedHTTPServer((host, preferred_port), OdikyuBlockPageHandler)
    except OSError as exc:
        print(f"[!] Warning: Could not bind HTTP block page to port {preferred_port} ({exc}). Trying fallback port {alt_port}...")
        try:
            server = ThreadedHTTPServer((host, alt_port), OdikyuBlockPageHandler)
            actual_port = alt_port
        except OSError as exc2:
            print(f"[!] Error: Could not bind fallback HTTP port {alt_port}: {exc2}")
            raise

    print(f"[*] Block Page HTTP Server running on http://{host}:{actual_port}/")
    print(f"[*] Dashboard & Threat Monitor accessible at http://{config.SERVER_HOSTNAME}:{actual_port}/")
    return server, actual_port


def start_block_page_server_thread(
    host: str = "0.0.0.0",
    port: int | None = None,
    tm: ThreatIntelligenceManager | None = None,
) -> tuple[threading.Thread, ThreadedHTTPServer, int]:
    """Start the HTTP block page server in a background daemon thread."""
    server, actual_port = run_block_page_server(host=host, port=port, tm=tm)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return thread, server, actual_port


if __name__ == "__main__":
    server, port = run_block_page_server()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down HTTP Block Page Server.")
        server.shutdown()
        server.server_close()
