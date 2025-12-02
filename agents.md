Project quicknotes for operators
================================

Start/stop locally
- Use `./start.sh` to start Docker (InfluxDB + Grafana), wait for Influx health, and run `monitor.py` (prefers `.venv/bin/python`).
- To run monitor only (assuming services already up): `.venv/bin/python monitor.py`

Autostart (systemd)
- Unit file: `/etc/systemd/system/wan-monitor.service`
- Exec: `/bin/bash /home/pi/WAN_LAN_WLAN_Performance_Monitor/start.sh`
- User: `pi`; Restart=always; WorkingDirectory: project root
- Commands:
  - Enable/start: `sudo systemctl enable --now wan-monitor.service`
  - Status: `systemctl status --no-pager wan-monitor.service`
  - Logs: `journalctl -u wan-monitor.service -f`
  - Stop/disable: `sudo systemctl stop wan-monitor.service`; `sudo systemctl disable wan-monitor.service`

Docker/Grafana/Influx
- `docker compose up -d` uses `.env` for InfluxDB/Grafana init; Grafana mounts `./provisioning`.
- Datasource provisioning: `provisioning/datasources/influx.yml` (InfluxQL, URL `http://influxdb:8086`, token/org/bucket from `.env`).
- Dashboard provisioning: `provisioning/dashboards/wan-wlan-performance.json` via `provisioning/dashboards/dashboards.yaml`.
- Grafana: http://localhost:3000 (admin creds from `.env`).
- InfluxDB: http://localhost:8086 (token from `.env`, org/bucket `wan-monitor` by default).

Monitor highlights
- Loads `.env` automatically on start; `INFLUX_TOKEN` falls back to `INFLUXDB_TOKEN`.
- Metrics:
  - `ping_latency` (latency_ms; interface, host tags)
  - `speedtest` (download_mbps, upload_mbps, ping_ms; interface tag)
  - `download_test` (bandwidth_mbps, file_size_bytes, duration_seconds; interface, file tags)
- Speedtest uses sivel speedtest-cli with `--json`.

Repo notes
- `.gitignore` ignores `data/` (Docker volumes). Provisioning and start script are committed.
