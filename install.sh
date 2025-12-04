#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a fresh Raspberry Pi to run the WAN/LAN/WLAN Performance Monitor.
# Installs system deps, Docker, Python venv + requirements, and seeds .env.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    *)
      shift
      ;;
  esac
done
cd "$ROOT_DIR"

SUDO=""
if [[ $EUID -ne 0 ]]; then
  SUDO="sudo"
fi

log() { printf "==> %s\n" "$*"; }
dry() { if [[ $DRY_RUN -eq 1 ]]; then printf "[dry-run] %s\n" "$*"; fi; }

install_packages() {
  log "Updating apt cache..."
  if [[ $DRY_RUN -eq 0 ]]; then $SUDO apt-get update -y; else dry "skip: apt-get update -y"; fi
  log "Installing system packages..."
  if [[ $DRY_RUN -eq 0 ]]; then
    $SUDO apt-get install -y \
      python3-venv python3-pip \
      iputils-ping wget curl \
      docker.io docker-compose-plugin
    log "Enabling and starting Docker..."
    $SUDO systemctl enable --now docker
  else
    dry "skip: apt-get install -y python3-venv python3-pip iputils-ping wget curl docker.io docker-compose-plugin"
    dry "skip: systemctl enable --now docker"
  fi
}

setup_venv() {
  if [[ ! -d ".venv" ]]; then
    log "Creating virtual environment..."
    if [[ $DRY_RUN -eq 0 ]]; then python3 -m venv .venv; else dry "skip: python3 -m venv .venv"; fi
  fi
  log "Installing Python requirements..."
  if [[ $DRY_RUN -eq 0 ]]; then
    . .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
  else
    dry "skip: source .venv/bin/activate"
    dry "skip: pip install --upgrade pip"
    dry "skip: pip install -r requirements.txt"
  fi
}

seed_env() {
  if [[ -f ".env" ]]; then
    log ".env already present; leaving as-is"
    return
  fi
  read -r -p "No .env found. Copy .env.example to .env now? [y/N] " ans
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    log "Seeding .env from .env.example"
    if [[ $DRY_RUN -eq 0 ]]; then cp .env.example .env; else dry "skip: cp .env.example .env"; fi
  else
    log "Skipping .env creation; create it manually before starting."
  fi
}

setup_systemd() {
  read -r -p "Create and enable systemd service wan-monitor.service? [y/N] " ans
  if [[ ! "$ans" =~ ^[Yy]$ ]]; then
    log "Skipping systemd setup."
    return
  fi

  SERVICE_PATH="/etc/systemd/system/wan-monitor.service"
  log "Writing systemd unit to $SERVICE_PATH"
  if [[ $DRY_RUN -eq 0 ]]; then
    cat <<'EOF' | $SUDO tee "$SERVICE_PATH" >/dev/null
[Unit]
Description=WAN/LAN/WLAN Performance Monitor
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/WAN_LAN_WLAN_Performance_Monitor
ExecStart=/bin/bash /home/pi/WAN_LAN_WLAN_Performance_Monitor/start.sh
Restart=always
RestartSec=10
Environment=PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

[Install]
WantedBy=multi-user.target
EOF

  log "Enabling and starting wan-monitor.service..."
  $SUDO systemctl daemon-reload
  $SUDO systemctl enable --now wan-monitor.service
  else
    dry "skip: write $SERVICE_PATH"
    dry "skip: systemctl daemon-reload"
    dry "skip: systemctl enable --now wan-monitor.service"
  fi
}

setup_wlan_cron() {
  read -r -p "Add cron job to restart wlan0 every 6 hours? [y/N] " ans
  if [[ ! "$ans" =~ ^[Yy]$ ]]; then
    log "Skipping WLAN restart cron."
    return
  fi

  CRON_FILE="/etc/cron.d/wan-monitor-wlan-restart"
  SCRIPT_PATH="$ROOT_DIR/scripts/restart_wlan.sh"
  log "Writing cron job to $CRON_FILE (runs every 6h)"

  if [[ $DRY_RUN -eq 0 ]]; then
    $SUDO chmod +x "$SCRIPT_PATH"
    cat <<EOF | $SUDO tee "$CRON_FILE" >/dev/null
# Restart wlan0 periodically to recover flaky Wi-Fi
0 */6 * * * root /bin/bash $SCRIPT_PATH >> /var/log/wan-wlan-restart.log 2>&1
EOF
    $SUDO chmod 644 "$CRON_FILE"
  else
    dry "skip: chmod +x $SCRIPT_PATH"
    dry "skip: write $CRON_FILE with 0 */6 * * * root /bin/bash $SCRIPT_PATH"
    dry "skip: chmod 644 $CRON_FILE"
  fi
}

main() {
  install_packages
  setup_venv
  seed_env
  setup_systemd
  setup_wlan_cron
  log "Bootstrap complete. Next steps:"
  log "  1) Review and edit .env (tokens, passwords, URLs)."
  log "  2) Start the stack: ./start.sh"
  log "  3) If you skipped systemd setup, you can add it later via install.sh."
}

main "$@"
