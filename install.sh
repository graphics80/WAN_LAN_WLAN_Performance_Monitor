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

install_packages() {
  log "Updating apt cache..."
  if [[ $DRY_RUN -eq 0 ]]; then $SUDO apt-get update -y; else log "[dry-run] skip apt update"; fi
  log "Installing system packages..."
  if [[ $DRY_RUN -eq 0 ]]; then
    $SUDO apt-get install -y \
      python3-venv python3-pip \
      iputils-ping wget curl \
      docker.io docker-compose-plugin
    log "Enabling and starting Docker..."
    $SUDO systemctl enable --now docker
  else
    log "[dry-run] skip apt install and Docker enable"
  fi
}

setup_venv() {
  if [[ ! -d ".venv" ]]; then
    log "Creating virtual environment..."
    if [[ $DRY_RUN -eq 0 ]]; then python3 -m venv .venv; else log "[dry-run] skip venv create"; fi
  fi
  log "Installing Python requirements..."
  if [[ $DRY_RUN -eq 0 ]]; then
    . .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
  else
    log "[dry-run] skip pip install"
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
    if [[ $DRY_RUN -eq 0 ]]; then cp .env.example .env; else log "[dry-run] skip env copy"; fi
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
    log "[dry-run] skip writing/starting systemd service"
  fi
}

main() {
  install_packages
  setup_venv
  seed_env
  setup_systemd
  log "Bootstrap complete. Next steps:"
  log "  1) Review and edit .env (tokens, passwords, URLs)."
  log "  2) Start the stack: ./start.sh"
  log "  3) If you skipped systemd setup, you can add it later via install.sh."
}

main "$@"
