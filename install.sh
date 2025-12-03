#!/usr/bin/env bash
set -euo pipefail

# Bootstrap a fresh Raspberry Pi to run the WAN/LAN/WLAN Performance Monitor.
# Installs system deps, Docker, Python venv + requirements, and seeds .env.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

SUDO=""
if [[ $EUID -ne 0 ]]; then
  SUDO="sudo"
fi

log() { printf "==> %s\n" "$*"; }

install_packages() {
  log "Updating apt cache..."
  $SUDO apt-get update -y
  log "Installing system packages..."
  $SUDO apt-get install -y \
    python3-venv python3-pip \
    iputils-ping wget curl \
    docker.io docker-compose-plugin
  log "Enabling and starting Docker..."
  $SUDO systemctl enable --now docker
}

setup_venv() {
  if [[ ! -d ".venv" ]]; then
    log "Creating virtual environment..."
    python3 -m venv .venv
  fi
  log "Installing Python requirements..."
  . .venv/bin/activate
  pip install --upgrade pip
  pip install -r requirements.txt
}

seed_env() {
  if [[ ! -f ".env" ]]; then
    log "Seeding .env from .env.example"
    cp .env.example .env
  else
    log ".env already present; leaving as-is"
  fi
}

main() {
  install_packages
  setup_venv
  seed_env
  log "Bootstrap complete. Next steps:"
  log "  1) Review and edit .env (tokens, passwords, URLs)."
  log "  2) Start the stack: ./start.sh"
  log "  3) Optional: enable systemd service (see README)."
}

main "$@"
