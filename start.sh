#!/usr/bin/env bash
set -euo pipefail

# Start Docker services (InfluxDB + Grafana) and then run the monitor.

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Start the Docker stack (uses .env automatically).
docker compose up -d

# Wait briefly for InfluxDB to become reachable.
INFLUX_URL_DEFAULT="http://localhost:8086"
INFLUX_URL="${INFLUX_URL:-$INFLUX_URL_DEFAULT}"
for i in {1..15}; do
  if curl -fsS "$INFLUX_URL/health" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

# Choose Python: prefer local venv if available.
if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PYTHON="$ROOT_DIR/.venv/bin/python"
else
  PYTHON="$(command -v python3 || command -v python)"
fi

exec "$PYTHON" "$ROOT_DIR/monitor.py"
