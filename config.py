"""
Configuration and Environment Loader for Odikyu DNS Shield (dns.odikyu.tech)
=============================================================================
Automatically loads key-value pairs from .env without external dependencies
and provides validated, central configuration values for the entire project.
"""

from __future__ import annotations

import os
import pathlib


def load_dotenv(env_path: str | None = None) -> dict[str, str]:
    """
    Load environment variables from a .env file into os.environ.
    Preserves existing environment variables. Supports comments (#),
    quoted strings, and export prefixes.
    """
    if env_path is None:
        # Default to .env in current directory or project root
        base_dir = pathlib.Path(__file__).resolve().parent
        env_path = str(base_dir / ".env")

    loaded: dict[str, str] = {}
    if not os.path.isfile(env_path):
        return loaded

    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue

                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()

                # Strip surrounding single or double quotes
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]

                if key and key not in os.environ:
                    os.environ[key] = val
                    loaded[key] = val
    except Exception as exc:
        print(f"[!] Warning: Failed to parse .env file at {env_path}: {exc}")

    return loaded


# Automatically load .env on import
load_dotenv()

# ---------------------------------------------------------------------------
# Central Configuration Settings
# ---------------------------------------------------------------------------

# Domain & Server
SERVER_HOSTNAME = os.getenv("SERVER_HOSTNAME", "dns.odikyu.tech")
DNS_LISTEN_IP = os.getenv("DNS_LISTEN_IP", "0.0.0.0")
DNS_PORT = int(os.getenv("DNS_PORT", "53"))

# Block Page / HTTP Warning Server (Render sets the PORT variable automatically)
BLOCK_PAGE_PORT = int(os.getenv("PORT", os.getenv("BLOCK_PAGE_PORT", "80")))
BLOCK_PAGE_IP = os.getenv("BLOCK_PAGE_IP", "127.0.0.1")
BLOCK_PAGE_ALT_PORT = int(os.getenv("BLOCK_PAGE_ALT_PORT", "8080"))

# Threat DB & Feeds
THREAT_DB_PATH = os.getenv("THREAT_DB_PATH", "threats.db")
SYNC_INTERVAL_SECONDS = int(os.getenv("SYNC_INTERVAL_SECONDS", "7200"))
DOH_SERVER = os.getenv("DOH_SERVER", "https://cloudflare-dns.com/dns-query")

# Policy
BLOCK_SUSPICIOUS = os.getenv("BLOCK_SUSPICIOUS", "true").lower() in ("1", "true", "yes")

# Google AI Studio / Gemma Configuration
GEMMA_API_KEY = os.getenv("GEMMA_API_KEY", "")
GEMMA_MODEL_NAME = os.getenv("GEMMA_MODEL_NAME", "gemma-4-31b-it")
GEMMA_API_BASE = os.getenv("GEMMA_API_BASE", "https://generativelanguage.googleapis.com")
AI_INSPECTION_ENABLED = os.getenv("AI_INSPECTION_ENABLED", "true").lower() in ("1", "true", "yes")
AUTO_INSPECT_SUSPICIOUS = os.getenv("AUTO_INSPECT_SUSPICIOUS", "true").lower() in ("1", "true", "yes")
