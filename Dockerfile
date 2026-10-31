# Multi-platform production container for Odikyu DNS Shield (dns.odikyu.tech)
FROM python:3.11-slim

# Prevent python from buffering stdout/stderr and writing bytecode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies & headless Chromium for visual website screenshots
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    ca-certificates \
    curl \
    libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application files
COPY config.py threat_manager.py website_inspector.py block_page_server.py dns_proxy.py ./

# Create screenshot and cache storage directories
RUN mkdir -p /app/screenshots

# Grant python binary capability to bind to privileged ports (53, 80) without root
RUN setcap 'cap_net_bind_service=+ep' /usr/local/bin/python3.11

# Expose DNS (UDP & TCP 53) and Warning HTTP Server (TCP 80)
EXPOSE 53/udp 53/tcp 80/tcp

# Healthcheck testing HTTP block server and DNS query
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:80/healthz || exit 1

# Launch DNS Proxy and Warning Server
CMD ["python", "dns_proxy.py"]
