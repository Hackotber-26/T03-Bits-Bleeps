# Odikyu DNS Shield (dns.odikyu.tech)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-brightgreen.svg)](https://python.org)
[![Docker: Ready](https://img.shields.io/badge/Docker-Ready-2496ED.svg)](docker-compose.yml)
[![AI Engine: Gemma 4 31B IT](https://img.shields.io/badge/AI%20Engine-Gemma--4--31b--it-8B5CF6.svg)](https://ai.google.dev/)

An enterprise-grade, high-performance **Proxy DNS Server** designed for deployment at **`dns.odikyu.tech`**. It protects users from phishing, malware, and credential theft by intercepting malicious queries, evaluating undetectable sites with **Gemma (`gemma-4-31b-it`)**, and serving an informative **HTTP Security Warning Page**.

---

## Architecture Overview

```
                           +-----------------------------------------------+
                           |          Client (PC / Mobile / Router)        |
                           +-----------------------------------------------+
                                     |                           |
                                     | (1) UDP 53 DNS Query      | (4) HTTP Request
                                     v                           v
+----------------------------------------------------+   +------------------------------------+
|            ODIKYU PROXY DNS SERVER                 |   |      HTTP WARNING / BLOCK SERVER   |
|                 (UDP Port 53)                      |   |             (HTTP Port 80)         |
|----------------------------------------------------|   |------------------------------------|
|  a. Fast Local Threat Match (< 0.1ms)              |   | Intercepts Host header:            |
|     - threats.db (PhishTank, OpenPhish)            |   | - If blocked: Renders Warning Page |
|     - ai_inspection_cache (Gemma verdicts)         |   |   with score, evidence, and advice |
|                                                    |   | - If dns.odikyu.tech:              |
|  b. Transparent Weighted Risk Scoring              |   |   Renders Management Console       |
|     - HIGH RISK (Score 100) -> Return BLOCK_PAGE_IP|   | - /api/check & /api/inspect        |
|     - SUSPICIOUS (35-75)    -> Caution / Inspect   |   +------------------------------------+
|     - LOW RISK (0-34)       -> Upstream DoH        |                     ^
+----------------------------------------------------+                     |
           |                           |                                   |
           | (2) Clean Domains         | (3) Suspicious Domains            |
           v                           v                                   |
+---------------------+    +------------------------------------------+    |
| RFC 8484 DoH Server |    |  Async Gemma-4-31b-it Website Inspector  |----+
| Cloudflare 1.1.1.1  |    |  - Headless Browser Screenshot (Edge/Chr)|
+---------------------+    |  - Network Telemetry (TLS, Form, Headers)|
                           |  - Multimodal Vision-Language Evaluation |
                           |  - Saves to threats.db cache & blocklist |
                           +------------------------------------------+
```

---

## Key Features

1. **Informative HTTP Warning & Block Page Server (`block_page_server.py`)**:
   - Intercepts visits to blocked domains and presents a modern, responsive warning page detailing:
     - Danger Tier (`HIGH RISK` or `SUSPICIOUS`) & Threat Score (`X/100`)
     - Target domain requested
     - Detection source (PhishTank, OpenPhish, or Gemma AI)
     - Triggered technical rules (credential forms, high Shannon entropy, deceptive brands)
     - Security advice explaining why the page was blocked.
   - Built-in **Management Dashboard** when accessing `http://dns.odikyu.tech/` or `/admin`:
     - Live server status & query statistics
     - Threat intelligence lookup tool
     - On-demand Gemma AI website inspection tool
     - Recent blocked query logs with timestamps and client IPs.

2. **Multimodal Website Inspection (`gemma-4-31b-it`)**:
   - Inspects sites that are undetectable by conventional static blocklists.
   - Captures high-fidelity full-viewport visual screenshots using headless browser automation.
   - Extracts complete network request telemetry (redirect chains, HTTP status, TLS cert issuer, remote IP, password fields, cross-domain form actions).
   - Prompts Google AI Studio's **`gemma-4-31b-it`** multimodal model to evaluate brand impersonation and credential harvesting.
   - Automatically caches inspection results and adds confirmed threats to the local SQLite database.

3. **Sub-Millisecond Threat Intelligence Engine**:
   - Stores over 25,000+ confirmed malicious indicators in a local SQLite database (`threats.db`) running in Write-Ahead Logging (`WAL`) mode with covering indexes.
   - Background thread periodically synchronizes trusted feeds (PhishTank compressed bulk CSV with ETag change checks, OpenPhish feed) with zero DNS query latency.
   - Hierarchical subdomain matching: blocking `evil-phish.com` automatically blocks `*.evil-phish.com`.

4. **Transparent Rule-Based Weighted Scoring**:
   - Eliminates arbitrary black-box scores:
     - **HIGH RISK (Score: 100)**: Confirmed malicious domain from a trusted feed. Action: `Block`.
     - **SUSPICIOUS (Score: 35–75)**: Heuristic suspicion (brand keywords, punycode, password inputs, suspicious TLDs, entropy anomalies). Action: `Caution` & asynchronous Gemma inspection.
     - **LOW RISK (Score: 0–34)**: Whitelisted or clean infrastructure. Action: `Allow`.

---

## Quick Start & Configuration

### 1. Environment Configuration (`.env`)
The project reads settings automatically from `.env`:

```ini
# Google AI Studio API Key for Gemma-4-31b-it
GEMMA_API_KEY=your_google_ai_studio_api_key_here
GEMMA_MODEL_NAME=gemma-4-31b-it
GEMMA_API_BASE=https://generativelanguage.googleapis.com

# Server & Domain Configuration
SERVER_HOSTNAME=dns.odikyu.tech
DNS_LISTEN_IP=0.0.0.0
DNS_PORT=53

# Block Page / Warning Page Configuration
# Set to the public IPv4 of dns.odikyu.tech in production (or 127.0.0.1 locally)
BLOCK_PAGE_IP=127.0.0.1
BLOCK_PAGE_PORT=80
BLOCK_PAGE_ALT_PORT=8080

# Threat Intelligence & Policy
BLOCK_SUSPICIOUS=true
AI_INSPECTION_ENABLED=true
AUTO_INSPECT_SUSPICIOUS=true

# Upstream DNS-over-HTTPS (RFC 8484)
DOH_SERVER=https://cloudflare-dns.com/dns-query
THREAT_DB_PATH=threats.db
SYNC_INTERVAL_SECONDS=7200

# PhishTank feed (developer requirements: https://www.phishtank.com/developer_info)
#PHISHTANK_API_KEY=your_phishtank_app_key
PHISHTANK_USER_AGENT=odikyu-dns-shield/2.0 (+https://dns.odikyu.tech)
```

### PhishTank feed compliance

Every request the server makes to `data.phishtank.com` follows PhishTank's developer requirements:

- **Descriptive User-Agent** on all GET *and* HEAD requests (`odikyu-dns-shield/2.0 (+https://dns.odikyu.tech)`, overridable via `PHISHTANK_USER_AGENT`) — blank/generic agents get rate limited or extra security challenges.
- **Bulk lookups use the downloadable database** `online-valid.csv.gz` (compressed), with an automatic fallback to the documented plain `online-valid.csv`.
- **Application key** (`PHISHTANK_API_KEY`): switches to the keyed URL `https://data.phishtank.com/data/<key>/online-valid.csv.gz` and enables **unlimited HTTP HEAD requests** to compare the `ETag` — since files update hourly on the hour, unchanged files are never re-downloaded (checked each `SYNC_INTERVAL_SECONDS` cycle).

---

## Deployment to `dns.odikyu.tech`

### Method A: 1-Click Docker Compose (Recommended)

1. Clone repository to your VPS:
   ```bash
   git clone https://github.com/your-repo/Odikyu_dns.git /opt/odikyu-dns
   cd /opt/odikyu-dns
   ```
2. Verify `.env` values (set `BLOCK_PAGE_IP` to your server's public IP).
3. Start container:
   ```bash
   docker compose up -d
   ```
4. Verify running services:
   ```bash
   docker compose logs -f
   ```

### Method B: Native Linux Systemd Deployment

1. Run the included automated deploy script:
   ```bash
   sudo bash deploy.sh
   ```
2. Check service status:
   ```bash
   sudo systemctl status odikyu-dns
   ```
3. View real-time logs:
   ```bash
   sudo journalctl -u odikyu-dns -f
   ```

### Method C: Local Testing

Run the combined server (DNS Proxy + HTTP Warning Server):
```bash
# Windows (Run PowerShell as Administrator):
python dns_proxy.py

# Linux:
sudo python3 dns_proxy.py
```

---

## CLI & API Reference

### CLI Commands

```bash
# Check risk score for any domain locally
python threat_manager.py check paypal-security-update.xyz

# Run Gemma multimodal website inspection
python threat_manager.py inspect suspicious-login.top

# View threat database statistics & feed breakdown
python threat_manager.py stats

# Manually trigger threat feed synchronization
python threat_manager.py sync
```

### HTTP API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `http://dns.odikyu.tech/` | `GET` | Threat Intelligence Management Console |
| `http://dns.odikyu.tech/api/check?domain=example.com` | `GET` | Returns instant JSON risk assessment |
| `http://dns.odikyu.tech/api/inspect?domain=example.com` | `GET` | Triggers Gemma AI multimodal inspection |
| `http://dns.odikyu.tech/api/stats` | `GET` | Database threat statistics & feed health |
| `http://dns.odikyu.tech/healthz` | `GET` | Healthcheck (HTTP 200 OK) |

---

## Client DNS Configuration

To protect devices with Odikyu DNS Shield, set their DNS resolver to the IP of `dns.odikyu.tech`:

- **Windows**: `Settings` > `Network & Internet` > `Wi-Fi / Ethernet` > `DNS server assignment: Manual` > `IPv4: <IP of dns.odikyu.tech>`.
- **macOS / Linux**: Edit `/etc/resolv.conf` to add `nameserver <IP of dns.odikyu.tech>`.
- **Router**: Set Primary DNS to `<IP of dns.odikyu.tech>` to protect the entire home or office network.
