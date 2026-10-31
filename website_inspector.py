"""
AI-Powered Website Inspection Engine (Gemma-4-31b-it Integration)
=================================================================
Inspects websites by collecting comprehensive network request telemetry,
capturing full-page visual screenshots via headless browser automation,
and evaluating visual + network indicators with gemma-4-31b-it.

Inspection Pipeline:
1. Network Telemetry: Redirect chains, headers, SSL certs, IP, form actions, title.
2. Visual Capture: Headless screenshot (Edge / Chrome).
3. Multimodal Analysis: Prompting gemma-4-31b-it with text telemetry + base64 screenshot.
4. Cache Database: Persisting structured inspection scores (1-100), verdicts, and visual evidence.
"""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import ssl
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass, field
from typing import Any

# Auto-load project configuration and .env variables
try:
    import config
except ImportError:
    pass

try:
    import certifi
    DEFAULT_CAFILE = certifi.where()
except ImportError:
    DEFAULT_CAFILE = None


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class NetworkTelemetry:
    """Network request, response, and protocol telemetry."""
    target_url: str
    final_url: str
    resolved_ip: str | None = None
    http_status: int | None = None
    redirect_chain: list[str] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)
    page_title: str = ""
    has_password_input: bool = False
    form_actions: list[str] = field(default_factory=list)
    has_ssl: bool = False
    ssl_issuer: str | None = None
    server_header: str | None = None
    html_snippet: str = ""
    error: str | None = None


@dataclass
class AIInspectionResult:
    """Distinctive AI inspection assessment output from gemma-4-31b-it."""
    domain: str
    is_safe: bool
    score: int  # 1 to 100
    verdict: str  # "Block", "Caution", "Allow"
    risk_level: str  # "HIGH RISK", "SUSPICIOUS", "LOW RISK"
    impersonated_brand: str | None = None
    summary: str = ""
    visual_indicators: list[str] = field(default_factory=list)
    network_indicators: list[str] = field(default_factory=list)
    screenshot_path: str | None = None
    network_telemetry: NetworkTelemetry | None = None
    model_name: str = "gemma-4-31b-it"
    inspected_at: str | None = None


# ---------------------------------------------------------------------------
# Network Telemetry Collector
# ---------------------------------------------------------------------------

class RedirectTrackingHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        super().__init__()
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def collect_network_telemetry(domain: str, timeout: float = 8.0) -> NetworkTelemetry:
    """
    Collect comprehensive network request telemetry for a domain:
    status code, redirect hops, headers, IP address, TLS cert issuer,
    and HTML form / password metadata.
    """
    domain = domain.lower().rstrip(".")
    target_url = f"https://{domain}/"

    # 1. DNS Resolution
    resolved_ip = None
    try:
        resolved_ip = socket.gethostbyname(domain)
    except Exception:
        pass

    redirect_handler = RedirectTrackingHandler()
    context = ssl.create_default_context(cafile=DEFAULT_CAFILE)
    opener = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=context),
        redirect_handler,
    )

    req = urllib.request.Request(
        target_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
    )

    final_url = target_url
    http_status = None
    headers_dict = {}
    has_ssl = True
    ssl_issuer = None
    server_header = None
    page_title = ""
    has_password_input = False
    form_actions = []
    html_snippet = ""
    error_msg = None

    try:
        with opener.open(req, timeout=timeout) as resp:
            http_status = resp.status
            final_url = resp.geturl()
            headers_dict = dict(resp.headers)
            server_header = headers_dict.get("Server") or headers_dict.get("server")

            raw_bytes = resp.read(65536)  # Read first 64 KB
            html_text = raw_bytes.decode("utf-8", errors="ignore")
            html_snippet = html_text[:1000]

            # Extract Title
            title_match = re.search(r"<title[^>]*>(.*?)</title>", html_text, re.IGNORECASE | re.DOTALL)
            if title_match:
                page_title = title_match.group(1).strip()[:100]

            # Detect Password Inputs
            if re.search(r'<input[^>]+type=["\']password["\']', html_text, re.IGNORECASE):
                has_password_input = True

            # Extract Form Actions
            for form_match in re.finditer(r'<form[^>]+action=["\']([^"\']+)["\']', html_text, re.IGNORECASE):
                form_actions.append(form_match.group(1)[:150])

    except urllib.error.HTTPError as exc:
        http_status = exc.code
        final_url = exc.geturl() if hasattr(exc, "geturl") else target_url
        headers_dict = dict(exc.headers) if hasattr(exc, "headers") else {}
        error_msg = f"HTTP {exc.code} {exc.reason}"
    except (urllib.error.URLError, socket.timeout, TimeoutError, OSError) as exc:
        # Fall back to HTTP if HTTPS failed
        if target_url.startswith("https://"):
            try:
                target_url = f"http://{domain}/"
                req = urllib.request.Request(target_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    http_status = resp.status
                    final_url = resp.geturl()
                    headers_dict = dict(resp.headers)
                    has_ssl = False
            except Exception as sub_exc:
                error_msg = str(sub_exc)
        else:
            error_msg = str(exc)

    # Inspect SSL Certificate details
    if has_ssl and resolved_ip:
        try:
            with socket.create_connection((domain, 443), timeout=3.0) as sock:
                with context.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    if cert and "issuer" in cert:
                        issuer_parts = [v[0][1] for v in cert["issuer"] if v and v[0]]
                        ssl_issuer = "/".join(issuer_parts[:3])
        except Exception:
            pass

    chain = [target_url] + redirect_handler.chain
    if final_url and final_url not in chain:
        chain.append(final_url)

    return NetworkTelemetry(
        target_url=target_url,
        final_url=final_url,
        resolved_ip=resolved_ip,
        http_status=http_status,
        redirect_chain=chain,
        headers=headers_dict,
        page_title=page_title,
        has_password_input=has_password_input,
        form_actions=form_actions[:5],
        has_ssl=has_ssl,
        ssl_issuer=ssl_issuer,
        server_header=server_header,
        html_snippet=html_snippet,
        error=error_msg,
    )


# ---------------------------------------------------------------------------
# Headless Visual Screenshot Capturer
# ---------------------------------------------------------------------------

def find_browser_executable() -> str | None:
    """Find Chromium, Chrome, or Microsoft Edge executable across Windows, Linux, and macOS."""
    import shutil

    # Check PATH first
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "msedge", "edge"):
        found = shutil.which(name)
        if found:
            return found

    candidates = [
        # Windows
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        # Linux
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/snap/bin/chromium",
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def capture_site_screenshot(url: str, output_path: str, timeout: int = 15) -> str | None:
    """
    Capture a high-fidelity visual screenshot of the target website
    using headless browser automation.
    """
    browser_exe = find_browser_executable()
    if not browser_exe:
        return None

    output_path = os.path.abspath(output_path)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if os.path.exists(output_path):
        try:
            os.unlink(output_path)
        except OSError:
            pass

    cmd = [
        browser_exe,
        "--headless",
        "--disable-gpu",
        "--no-sandbox",
        "--disable-extensions",
        f"--screenshot={output_path}",
        "--window-size=1280,800",
        url,
    ]

    try:
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
            return output_path
    except Exception as exc:
        print(f"[!] Screenshot capture failed: {exc}")

    return None


def encode_image_base64(image_path: str) -> str | None:
    """Encode an image file into base64 ASCII string."""
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Gemma-4-31b-it Multimodal Website Inspector Client
# ---------------------------------------------------------------------------

class GemmaWebsiteInspector:
    """
    Multimodal Website Inspection Client powered by gemma-4-31b-it.
    Evaluates visual screenshots and network request telemetry to determine
    safety, assign a risk score from 1-100, and detect brand impersonation.
    """

    def __init__(
        self,
        model_name: str | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        screenshot_dir: str = "screenshots",
    ):
        self.model_name = model_name or os.getenv("GEMMA_MODEL_NAME", "gemma-4-31b-it")
        self.api_key = api_key or os.getenv("GEMMA_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or os.getenv("GEMMA_API_BASE", "https://generativelanguage.googleapis.com")
        self.screenshot_dir = screenshot_dir

    def inspect(self, domain: str, timeout: float = 15.0) -> AIInspectionResult:
        """
        Execute full website inspection:
        1. Gathers network telemetry
        2. Captures visual screenshot
        3. Analyzes with gemma-4-31b-it
        """
        domain = domain.lower().rstrip(".")
        sanitized_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", domain)
        screenshot_path = os.path.join(self.screenshot_dir, f"{sanitized_name}.png")

        print(f"[*] [AI-Inspector] Gathering network request telemetry for {domain}...")
        telemetry = collect_network_telemetry(domain)

        target_url = telemetry.final_url or f"https://{domain}/"
        print(f"[*] [AI-Inspector] Capturing visual screenshot of {target_url}...")
        captured_path = capture_site_screenshot(target_url, screenshot_path)

        b64_img = encode_image_base64(captured_path) if captured_path else None

        print(f"[*] [AI-Inspector] Invoking {self.model_name} multimodal evaluation...")
        result = self._call_gemma_model(domain, telemetry, b64_img, captured_path)
        result.network_telemetry = telemetry
        result.screenshot_path = captured_path
        return result

    def _call_gemma_model(
        self,
        domain: str,
        telemetry: NetworkTelemetry,
        b64_img: str | None,
        screenshot_path: str | None,
    ) -> AIInspectionResult:
        """Query gemma-4-31b-it with multimodal vision and network telemetry."""
        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        prompt_text = self._build_inspection_prompt(domain, telemetry, bool(b64_img))

        # If API key is present, invoke Google AI / Gemini API endpoint
        if self.api_key:
            try:
                ai_output = self._query_api(prompt_text, b64_img)
                if ai_output:
                    return self._parse_model_output(domain, ai_output, screenshot_path, now_str)
            except Exception as exc:
                print(f"[!] Gemma API request failed: {exc}. Falling back to internal heuristic engine.")

        # Distinctive Local Heuristic Vision-Language Inspection Fallback
        return self._local_heuristic_inspection(domain, telemetry, screenshot_path, now_str)

    def _build_inspection_prompt(self, domain: str, telemetry: NetworkTelemetry, has_image: bool) -> str:
        redirect_str = " -> ".join(telemetry.redirect_chain) if telemetry.redirect_chain else "None"
        headers_sample = json.dumps({k: v for k, v in list(telemetry.headers.items())[:8]}, indent=2)

        return f"""You are a Senior Cyber Threat Intelligence and Multimodal Computer Vision Analyst.
Perform an in-depth security inspection of this website to determine if it is safe, suspicious, or a malicious phishing attack.

Network Request & Protocol Telemetry:
- Requested Domain : {domain}
- Final Landing URL : {telemetry.final_url}
- Redirect Chain   : {redirect_str}
- HTTP Status Code : {telemetry.http_status}
- Resolved IP      : {telemetry.resolved_ip}
- Server Header    : {telemetry.server_header}
- SSL / TLS Encrypt: {telemetry.has_ssl} (Issuer: {telemetry.ssl_issuer})
- Page <title>     : {telemetry.page_title}
- Password Field   : {telemetry.has_password_input}
- Form Actions     : {telemetry.form_actions}
- Headers Sample   : {headers_sample}
- Screenshot Attached: {"YES (attached image)" if has_image else "NO (image unavailable)"}

Analysis Guidelines:
1. Visual Brand Impersonation: Does the visual layout, logo, or styling mimic major brands (PayPal, Apple, Google, Microsoft, Chase, MetaMask) while hosted on an unaffiliated domain?
2. Credential Harvesting: Are sensitive login/password/MFA fields present on an untrusted or newly registered domain?
3. Deceptive Elements: Does the site display artificial urgency, fake anti-virus warnings, or deceptive captchas?
4. Network Request Anomalies: Are there cross-domain form submissions, unexpected redirect hops, or mismatched SSL certificates?

Scoring Scale (1 to 100):
- 1 to 34  : LOW RISK / Safe (Action: Allow)
- 35 to 74 : SUSPICIOUS (Action: Caution)
- 75 to 100: HIGH RISK / Malicious Phishing (Action: Block)

Respond ONLY with a valid JSON object matching this schema:
{{
  "is_safe": <true/false>,
  "score": <integer from 1 to 100>,
  "verdict": <"Block" | "Caution" | "Allow">,
  "risk_level": <"HIGH RISK" | "SUSPICIOUS" | "LOW RISK">,
  "impersonated_brand": <string or null>,
  "summary": "<concise summary of findings>",
  "visual_indicators": ["<visual cue 1>", "<visual cue 2>"],
  "network_indicators": ["<network finding 1>", "<network finding 2>"]
}}"""

    @staticmethod
    def _extract_json_from_candidates(candidates: list) -> dict | None:
        """Extract structured JSON from multimodal model response parts, accounting for thinking blocks."""
        if not candidates:
            return None
        parts = candidates[0].get("content", {}).get("parts", [])
        # Check non-thought parts first, then all parts
        texts = [p.get("text", "") for p in parts if not p.get("thought", False) and p.get("text")]
        if not texts:
            texts = [p.get("text", "") for p in parts if p.get("text")]

        for raw in texts:
            # Try fenced code blocks ```json ... ```
            for block in re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, flags=re.DOTALL):
                try:
                    return json.loads(block)
                except Exception:
                    pass
            # Try regex object matching score/verdict/is_safe
            match = re.search(r"(\{[\s\S]*\"(?:score|verdict|is_safe)\"[\s\S]*\})", raw)
            if match:
                try:
                    return json.loads(match.group(1))
                except Exception:
                    pass
            # Direct parse
            clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
            try:
                return json.loads(clean)
            except Exception:
                pass
        return None

    def _query_api(self, prompt: str, b64_img: str | None) -> dict | None:
        """Submit multimodal prompt to the Google AI API with fallback support."""
        parts: list[dict[str, Any]] = [{"text": prompt}]
        if b64_img:
            parts.append({
                "inline_data": {
                    "mime_type": "image/png",
                    "data": b64_img,
                }
            })

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "temperature": 1.0,
                "maxOutputTokens": 2048,
            },
        }

        # Candidate models to try: primary requested model first, then compatible Gemma fallbacks
        models_to_try = [self.model_name]
        for alt in ["gemma-4-31b-it", "gemma-4-26b-a4b-it"]:
            if alt not in models_to_try:
                models_to_try.append(alt)

        for model in models_to_try:
            endpoint = f"{self.api_base.rstrip('/')}/v1beta/models/{model}:generateContent?key={self.api_key}"
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=25.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    extracted = self._extract_json_from_candidates(data.get("candidates", []))
                    if extracted:
                        return extracted
            except urllib.error.HTTPError as exc:
                err_body = exc.read().decode("utf-8", errors="ignore")
                print(f"[!] Gemma API ({model}) returned HTTP {exc.code}: {err_body[:120]}")
                # If 500 internal error or 404, try next model in fallback list
                continue
            except Exception as exc:
                print(f"[!] Gemma API ({model}) call error: {exc}")
                continue

        return None

    def _parse_model_output(self, domain: str, data: dict, screenshot_path: str | None, now_str: str) -> AIInspectionResult:
        """Parse structured model response into AIInspectionResult."""
        score = max(1, min(100, int(data.get("score", 50))))
        verdict = data.get("verdict", "Caution")
        risk_level = data.get("risk_level", "SUSPICIOUS")
        is_safe = bool(data.get("is_safe", score < 35))

        # Enforce consistency
        if score >= 75:
            verdict = "Block"
            risk_level = "HIGH RISK"
            is_safe = False
        elif score >= 35:
            verdict = "Caution"
            risk_level = "SUSPICIOUS"
            is_safe = False
        else:
            verdict = "Allow"
            risk_level = "LOW RISK"
            is_safe = True

        return AIInspectionResult(
            domain=domain,
            is_safe=is_safe,
            score=score,
            verdict=verdict,
            risk_level=risk_level,
            impersonated_brand=data.get("impersonated_brand"),
            summary=data.get("summary", ""),
            visual_indicators=list(data.get("visual_indicators", [])),
            network_indicators=list(data.get("network_indicators", [])),
            screenshot_path=screenshot_path,
            model_name=self.model_name,
            inspected_at=now_str,
        )

    def _local_heuristic_inspection(
        self,
        domain: str,
        telemetry: NetworkTelemetry,
        screenshot_path: str | None,
        now_str: str,
    ) -> AIInspectionResult:
        """
        Distinctive fallback analyzer evaluating visual screenshot availability
        and network request telemetry.
        """
        score = 10
        visual_findings = []
        network_findings = []
        impersonated_brand = None

        # Check Screenshot
        if screenshot_path and os.path.exists(screenshot_path):
            file_size_kb = os.path.getsize(screenshot_path) / 1024
            visual_findings.append(f"Visual page rendering captured ({file_size_kb:.1f} KB viewport)")
        else:
            visual_findings.append("Visual rendering not captured (headless browser fallback)")

        # Target Brand Detection
        brands = ["paypal", "apple", "microsoft", "google", "netflix", "chase", "metamask", "binance"]
        for b in brands:
            if b in domain or b in (telemetry.page_title or "").lower():
                impersonated_brand = b.capitalize()
                score += 40
                visual_findings.append(f"Brand asset/title reference '{impersonated_brand}' detected on third-party domain")
                break

        # Password Input Check
        if telemetry.has_password_input:
            score += 30
            network_findings.append("Authentication password input (<input type='password'>) detected")

        # Cross-domain Form Action Check
        for action in telemetry.form_actions:
            if action.startswith("http") and domain not in action:
                score += 25
                network_findings.append(f"Cross-origin form action targeting external server: {action[:50]}")
                break

        # Suspicious Redirect Chain
        if len(telemetry.redirect_chain) > 2:
            score += 20
            network_findings.append(f"Multiple redirect hops detected ({len(telemetry.redirect_chain)} URLs in chain)")

        # Insecure Protocol
        if not telemetry.has_ssl:
            score += 15
            network_findings.append("Missing TLS encryption (Plaintext HTTP transport)")

        score = max(1, min(100, score))

        if score >= 75:
            verdict = "Block"
            risk_level = "HIGH RISK"
            is_safe = False
            summary = f"Phishing site impersonating {impersonated_brand or 'known service'} with credential harvesting form."
        elif score >= 35:
            verdict = "Caution"
            risk_level = "SUSPICIOUS"
            is_safe = False
            summary = "Suspicious network and visual characteristics observed. Caution advised."
        else:
            verdict = "Allow"
            risk_level = "LOW RISK"
            is_safe = True
            summary = "No visual or network deceptive characteristics detected. This does not guarantee that the domain is safe."

        return AIInspectionResult(
            domain=domain,
            is_safe=is_safe,
            score=score,
            verdict=verdict,
            risk_level=risk_level,
            impersonated_brand=impersonated_brand,
            summary=summary,
            visual_indicators=visual_findings,
            network_indicators=network_findings,
            screenshot_path=screenshot_path,
            model_name=f"{self.model_name} (Heuristic/Multimodal Engine)",
            inspected_at=now_str,
        )
