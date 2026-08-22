#!/usr/bin/env bash
# setup_monitoring.sh — One-time install of Prometheus + Grafana + nginx on the
# Hermes host (host-level infra; moved to its own JR Hermes VPS project S1 — was
# built inside hermes_v2's repo when this project didn't yet exist).
#
# Run once as root on 46.225.14.26:
#   bash /opt/hermes-vps/deploy/setup_monitoring.sh
#
# After running:
#   - Prometheus: http://localhost:9090 (internal only)
#   - Grafana:    https://www.artek-studio.com/grafana/
#                 Login: admin / $GRAFANA_ADMIN_PASSWORD (from this project's own .env)
set -euo pipefail

VPS_DIR="/opt/hermes-vps"
PROM_VERSION="2.51.2"   # update as needed; check https://github.com/prometheus/prometheus/releases
PROM_BIN="/usr/local/bin/prometheus"
PROM_DATA="/var/lib/prometheus"
ENV_FILE="/root/.hermes_vps/.env"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# ── Load .env for GRAFANA_ADMIN_PASSWORD ─────────────────────────────────────
# GRAFANA_ADMIN_PASSWORD used to live in hermes_v2's own .env (built there before
# this project existed) -- must be copied into this project's own .env as part
# of the S1 server migration, per HERMES_PLATFORM_STANDARD self-containment.
if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
fi
GRAFANA_ADMIN_PASSWORD="${GRAFANA_ADMIN_PASSWORD:-admin}"

# ── 1. Install Prometheus ─────────────────────────────────────────────────────
log "Installing Prometheus $PROM_VERSION ..."
if [[ ! -f "$PROM_BIN" ]]; then
    ARCH="linux-amd64"
    PROM_PKG="prometheus-${PROM_VERSION}.${ARCH}"
    cd /tmp
    curl -sLO "https://github.com/prometheus/prometheus/releases/download/v${PROM_VERSION}/${PROM_PKG}.tar.gz"
    tar xzf "${PROM_PKG}.tar.gz"
    cp "${PROM_PKG}/prometheus"        /usr/local/bin/prometheus
    cp "${PROM_PKG}/promtool"          /usr/local/bin/promtool
    rm -rf "${PROM_PKG}" "${PROM_PKG}.tar.gz"
    log "Prometheus binary installed"
else
    log "Prometheus already installed: $($PROM_BIN --version 2>&1 | head -1)"
fi

# Create prometheus user + data dir
id prometheus &>/dev/null || useradd --system --no-create-home --shell /bin/false prometheus
mkdir -p "$PROM_DATA"
chown prometheus:prometheus "$PROM_DATA"

# Install + start service
cp "$VPS_DIR/deploy/prometheus.service" /etc/systemd/system/prometheus.service
systemctl daemon-reload
systemctl enable --now prometheus.service
log "Prometheus service started"

# ── 2. Install Grafana ────────────────────────────────────────────────────────
log "Installing Grafana ..."
if ! command -v grafana-server &>/dev/null; then
    apt-get install -y apt-transport-https software-properties-common
    wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key
    echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" \
        > /etc/apt/sources.list.d/grafana.list
    apt-get update -q
    apt-get install -y grafana
    log "Grafana installed"
else
    log "Grafana already installed"
fi

# ── 3. Configure Grafana ──────────────────────────────────────────────────────
log "Configuring Grafana ..."

# Root URL + subpath (required for nginx /grafana/ proxy)
cat >> /etc/grafana/grafana.ini << 'EOF'

# Hermes v2 — nginx subpath config
[server]
domain = www.artek-studio.com
root_url = %(protocol)s://%(domain)s/grafana/
serve_from_sub_path = true

[security]
EOF
# Append admin password (not in heredoc to keep it out of history expansion)
echo "admin_password = ${GRAFANA_ADMIN_PASSWORD}" >> /etc/grafana/grafana.ini

# Disable anonymous access
sed -i 's/^;enabled = false/enabled = false/' /etc/grafana/grafana.ini

# ── 4. Symlink provisioning files (read from repo, live updates on git pull) ────
log "Installing Grafana provisioning (symlinks) ..."
rm -rf /etc/grafana/provisioning/datasources /etc/grafana/provisioning/dashboards
ln -sf "$VPS_DIR/deploy/grafana/provisioning/datasources" /etc/grafana/provisioning/datasources
ln -sf "$VPS_DIR/deploy/grafana/provisioning/dashboards"  /etc/grafana/provisioning/dashboards
chown -R grafana:grafana /etc/grafana/provisioning/
log "Symlinks created (dashboards/datasources → /opt/hermes-vps/deploy/grafana/provisioning/)"

# ── 5. Start Grafana ─────────────────────────────────────────────────────────
systemctl enable --now grafana-server
log "Grafana service started"

# ── 6. Copy nginx config + reload ────────────────────────────────────────────
# nginx.conf moved here whole (S1) -- it still contains hermes_v2's app-specific
# location blocks inline, this project just owns the single host-wide file now.
# The old /etc/nginx/sites-enabled/hermes_v2 file must be removed during cutover
# (not by this script -- see the migration handoff) so there's never a moment
# with two conflicting site files live.
log "Reloading nginx ..."
cp "$VPS_DIR/deploy/nginx.conf" /etc/nginx/sites-enabled/hermes-vps
nginx -t && systemctl reload nginx
log "nginx reloaded"

# ── 7. Verify ─────────────────────────────────────────────────────────────────
sleep 5
log "Checking Prometheus ..."
curl -sf "http://localhost:9090/-/healthy" && log "Prometheus: healthy" || log "WARNING: Prometheus not responding"

log "Checking Grafana ..."
curl -sf "http://localhost:3000/api/health" | python3 -m json.tool || log "WARNING: Grafana not responding"

log ""
log "=== Setup complete ==="
log "Prometheus: http://localhost:9090 (internal only)"
log "Grafana:    https://www.artek-studio.com/grafana/"
log "  Login:    admin / \$GRAFANA_ADMIN_PASSWORD"
log ""
log "Dashboard will auto-populate within 1 minute (first Prometheus scrape)."
