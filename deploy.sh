#!/usr/bin/env bash
# ==============================================================================
# Odikyu DNS Shield - Quick Deploy Script (dns.odikyu.tech)
# ==============================================================================
set -euo pipefail

echo "=========================================================="
echo "  Deploying Odikyu DNS Shield to dns.odikyu.tech"
echo "=========================================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run as root (or use sudo): sudo bash deploy.sh"
  exit 1
fi

APP_DIR="/opt/odikyu-dns"
mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/screenshots"

# Copy files
echo "[*] Installing application files to $APP_DIR..."
cp -r ./* "$APP_DIR/" 2>/dev/null || true

# Check if systemd-resolved is using port 53 and disable stub listener if needed
if systemctl is-active --quiet systemd-resolved; then
  echo "[*] Configuring systemd-resolved to free port 53..."
  sed -i 's/#DNSStubListener=yes/DNSStubListener=no/' /etc/systemd/resolved.conf || true
  sed -i 's/DNSStubListener=yes/DNSStubListener=no/' /etc/systemd/resolved.conf || true
  systemctl restart systemd-resolved || true
fi

# Install system dependencies
echo "[*] Ensuring Python 3 and Chromium dependencies are installed..."
if command -v apt-get &>/dev/null; then
  apt-get update -y
  apt-get install -y python3 chromium ca-certificates curl
fi

# Setup systemd service
echo "[*] Installing systemd service..."
cp "$APP_DIR/systemd/odikyu-dns.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable odikyu-dns.service
systemctl restart odikyu-dns.service

echo ""
echo "=========================================================="
echo "  Odikyu DNS Shield is active and listening!"
echo "  DNS Proxy       : UDP 53"
echo "  Warning Server  : HTTP 80"
echo "  Status check    : systemctl status odikyu-dns"
echo "  Live logs       : journalctl -u odikyu-dns -f"
echo "=========================================================="
