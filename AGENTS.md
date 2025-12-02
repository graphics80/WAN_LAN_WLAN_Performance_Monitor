# Repository Guidelines

## Project Structure & Module Organization
- `monitor.py`: Main runtime for WAN/LAN/WLAN monitoring (pings, speedtests, downloads).
- `start.sh`: Boots Docker stack (InfluxDB + Grafana) and runs the monitor.
- `provisioning/`: Grafana provisioning (datasource `datasources/influx.yml`, dashboard `dashboards/wan-wlan-performance.json`, provider `dashboards/dashboards.yaml`).
- `docker-compose.yml`: InfluxDB 2.x + Grafana services; loads `.env`.
- `data/`: Docker volumes (ignored by Git); contains Influx/Grafana state.
- `.env` / `.env.example`: Runtime and container configuration.

## Build, Test, and Development Commands
- Create venv + install deps: `python -m venv .venv && .venv/bin/pip install -r requirements.txt`.
- Start services only: `docker compose up -d`.
- Run monitor (auto-loads `.env`): `.venv/bin/python monitor.py`.
- One-shot start (services + monitor): `./start.sh`.
- Systemd service (autostart): `sudo systemctl enable --now wan-monitor.service`; status/logs: `systemctl status --no-pager wan-monitor.service`, `journalctl -u wan-monitor.service -f`.
- Inspect Grafana/Influx data quickly: `curl -s -u admin:admin http://localhost:3000/api/search`, `curl -s -H 'Authorization: Token <token>' http://localhost:8086/health`.

## Coding Style & Naming Conventions
- Python: prefer standard library types, explicit logging; keep functions small and interface-aware (`ping_latency`, `speedtest`, `download_test` measurements).
- Use snake_case for variables/functions; keep defaults in `AppConfig`.
- Avoid hard-coding credentials; always read from `.env`.

## Testing Guidelines
- No automated tests currently. When adding logic, prefer small, deterministic helpers and consider adding lightweight unit tests (pytest) under `tests/`.

## Commit & Pull Request Guidelines
- Commit messages: concise imperative (e.g., “Add start script”, “Provision Grafana dashboards”).
- Before PR: ensure monitor runs locally (`./start.sh`), services are healthy (`docker compose ps`), and provisioning files stay in `provisioning/`.
- Document changes in `README.md` or relevant ops notes when altering startup, provisioning, or metrics schema.

## Security & Configuration Tips
- Keep tokens in `.env`; `INFLUX_TOKEN` falls back to `INFLUXDB_TOKEN`.
- `data/` is ignored—don’t commit live Influx/Grafana state.
- Grafana datasource uses InfluxQL to `http://influxdb:8086`; dashboard provisioning expects uid `wanmonitor`. Adjust carefully if renaming. 
