# PellMon Docker Image
# Uses Debian's system Python for full dbus/gi compatibility

FROM debian:bookworm-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PELLMON_CONFIG=/etc/pellmon/pellmon.conf \
    PELLMON_DATA=/var/lib/pellmon

# Install Python and all system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    # RRDtool
    rrdtool \
    librrd-dev \
    python3-rrdtool \
    # D-Bus and GLib Python bindings
    dbus \
    python3-dbus \
    python3-gi \
    python3-gi-cairo \
    gir1.2-glib-2.0 \
    # Build dependencies
    gcc \
    pkg-config \
    # Network and utilities
    curl \
    procps \
    # Serial communication
    udev \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -r -g 999 pellmon && useradd -r -u 999 -g pellmon pellmon

# Create required directories
RUN mkdir -p /etc/pellmon /var/lib/pellmon /var/log/pellmon /var/run/pellmon \
    && chown -R pellmon:pellmon /var/lib/pellmon /var/log/pellmon /var/run/pellmon

# Set working directory
WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies using system Python with --break-system-packages
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application source
COPY src/ ./src/
COPY data/ ./data/

# Set ownership
RUN chown -R pellmon:pellmon /app

# Expose ports
EXPOSE 8081 8082

# Health check
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8081/ || exit 1

# Default to pellmon user
USER pellmon

# Volume mounts
VOLUME ["/etc/pellmon", "/var/lib/pellmon", "/var/log/pellmon"]

# Default command - use python3 (system Python)
CMD ["python3", "-m", "Pellmonweb.pellmonweb", "-C", "/etc/pellmon/pellmon.conf"]
