# PureBoot Controller Dockerfile
# Multi-stage build for minimal production image
FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# Production image
FROM python:3.11-slim-bookworm

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY src/ ./src/
COPY assets/ ./assets/

# Create directories for data
RUN mkdir -p /var/lib/pureboot/workflows /var/lib/pureboot/data /opt/pureboot/certs

# Create TFTP directory
RUN mkdir -p /tftp/bios /tftp/uefi /tftp/deploy

# Create non-root user for running the app
# (TFTP on port 69 requires CAP_NET_BIND_SERVICE capability instead of root)
RUN useradd -m -r pureboot && \
    chown -R pureboot:pureboot /var/lib/pureboot /opt/pureboot /tftp

# Environment variables
ENV PUREBOOT_HOST=0.0.0.0 \
    PUREBOOT_PORT=8080 \
    PUREBOOT_DATABASE__URL=sqlite+aiosqlite:///./data/pureboot.db \
    PUREBOOT_TFTP__ROOT=/tftp \
    PUREBOOT_TFTP__ENABLED=true \
    PUREBOOT_WORKFLOWS_DIR=/var/lib/pureboot/workflows \
    PYTHONUNBUFFERED=1

# Expose ports
# 8080 - HTTP API and Web UI
# 69 - TFTP (UDP)
# 4011 - Proxy DHCP (UDP, optional)
EXPOSE 8080 69/udp 4011/udp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Run as pureboot user
USER pureboot

# Run the application
CMD ["python", "-m", "src.main"]
