#!/usr/bin/env bash
set -euo pipefail

# Restart the systemd service so refreshed .env values are used (see README).

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SYSTEMCTL="$(command -v systemctl || true)"

if [[ -n "$SYSTEMCTL" ]]; then
  echo "Stopping wan-monitor.service..."
  sudo systemctl stop wan-monitor.service || echo "wan-monitor.service was not running"
else
  echo "systemctl not available; stopping monitor process directly..."
  pkill -f "python.*monitor.py" >/dev/null 2>&1 || true
fi

echo "Restarting Docker services..."
docker compose down

if [[ -n "$SYSTEMCTL" ]]; then
  echo "Starting wan-monitor.service..."
  exec sudo systemctl start wan-monitor.service
else
  echo "Starting monitor with refreshed environment via scripts/start.sh..."
  exec "$ROOT_DIR/scripts/start.sh"
fi
