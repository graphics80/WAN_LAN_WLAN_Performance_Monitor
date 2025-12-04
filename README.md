# WAN / LAN / WLAN Performance Monitor

Python script for a Raspberry Pi that measures network performance via the `eth0` and `wlan0` interfaces and stores the results in InfluxDB, ready to be visualized in Grafana.

## Features
- Ping latency for multiple targets every minute (per interface)
- Speedtest download/upload every 60 minutes (per interface) using the Speedtest CLI
- Download-based bandwidth checks every 5 minutes for 5 MB, 50 MB, and 80 MB files (per interface)
- HTTP end-to-end load tests with Locust (configurable targets/users, per interface)
- Metrics written to InfluxDB 2.x; Grafana dashboards can query the bucket directly

## Requirements
- Raspberry Pi (or any Linux host) with `eth0` and `wlan0`
- Python 3.10+
- `ping`, `wget`, and the `speedtest` CLI available in `PATH`
- Docker (for InfluxDB and Grafana)

## Installation
1. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install Python dependencies inside the venv:
   ```bash
   pip install -r requirements.txt
   ```
3. Install required CLI tools (host-level):
   ```bash

   # Speedtest CLI
   sudo pip install speedtest-cli
   # or use the Debian/Ubuntu package: sudo apt-get install speedtest-cli
   # ICMP + downloads rely on ping and wget
   sudo apt-get install iputils-ping wget
   ```
4. Copy `.env.example` to `.env` and adjust values (used by both the monitor and docker-compose):
   ```bash
   cp .env.example .env
   ```
   - `INFLUXDB_*` values configure the Docker containers.
   - `INFLUX_*` values are read by the Python monitor; `INFLUX_TOKEN` falls back to `INFLUXDB_TOKEN` so you can keep them identical.
5. Start InfluxDB + Grafana, which will be auto-configured from `.env`:
   ```bash
   docker compose up -d
   ```
6. Start the monitor locally from the activated venv (it auto-loads `.env`):
   ```bash
   python monitor.py
   ```

### One-shot start script
- Use `./scripts/start.sh` to launch Docker (InfluxDB + Grafana), wait briefly for Influx health, and then start the monitor (prefers `.venv/bin/python` if present). This script is used by the autostart service below. Thin wrappers remain at `./start.sh` and `./restart.sh` for backward compatibility.
- `./scripts/start.sh` also resets the Grafana admin password each time to the value in `.env` (`GRAFANA_PASSWORD`), so updates take effect even with a persistent data volume.
- Use `./scripts/restart.sh` to stop the systemd service (or the monitor process if systemd is unavailable), bring the Docker stack down, and start everything again so `.env` changes are applied.

### Bootstrap script
- Run `./install.sh` on a fresh Pi to install system dependencies (Docker + compose plugin, ping/wget, Python venv), create the venv and install requirements, optionally copy `.env.example` to `.env`, and optionally install/enable the `wan-monitor.service` systemd unit.
- `./install.sh` can also optionally install a cron job that restarts `wlan0` every 6 hours (uses `scripts/restart_wlan.sh`) to recover flaky Wi‑Fi links.
- `./install.sh --dry-run` prints each step it would take (apt installs, Docker enable, venv/pip steps, env copy, systemd write) without making changes.

### Optional WLAN auto-restart cron
- Script: `scripts/restart_wlan.sh` restarts a Wi‑Fi interface (default `wlan0`) and renews DHCP if `dhclient` is available.
- Enable via `./install.sh` when prompted, or manually create `/etc/cron.d/wan-monitor-wlan-restart` with:
  ```cron
  0 */6 * * * root /bin/bash /home/pi/WAN_LAN_WLAN_Performance_Monitor/scripts/restart_wlan.sh >> /var/log/wan-wlan-restart.log 2>&1
  ```
- Remove the cron job by deleting `/etc/cron.d/wan-monitor-wlan-restart`.

### Hardware recommendation
- A Raspberry Pi 5 with 8 GB RAM and at least 32 GB storage (SD or SSD), connected via both LAN and Wi‑Fi, is recommended for running the monitor, Docker stack, and Locust HTTP load tests.

### Autostart via systemd (Raspberry Pi / Linux)
1) Install the unit (already created during setup, but you can recreate it):
   ```bash
   cat <<'EOF' | sudo tee /etc/systemd/system/wan-monitor.service
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
   ```
2) Reload units and enable autostart:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable wan-monitor.service
   sudo systemctl start wan-monitor.service
   ```
3) Check status/logs:
   ```bash
   systemctl status --no-pager wan-monitor.service
   journalctl -u wan-monitor.service -f
   ```
4) Manage service:
   ```bash
   sudo systemctl stop wan-monitor.service
   sudo systemctl start wan-monitor.service
   sudo systemctl disable wan-monitor.service   # turn off autostart
   ```

### Grafana provisioning
- Datasource: provisioned from `provisioning/datasources/influx.yml` (InfluxQL, URL `http://influxdb:8086`, token/org/bucket from `.env`).
- Dashboards: provisioned from `provisioning/dashboards/wan-wlan-performance.json` via `provisioning/dashboards/dashboards.yaml`. On a fresh clone, `docker compose up -d` will load the dashboard automatically.

### Scheduling intervals
- `PING_INTERVAL_MINUTES` (default: 1)
- `SPEEDTEST_INTERVAL_MINUTES` (default: 60)
- `DOWNLOAD_INTERVAL_MINUTES` (default: 5)
- `HTTP_TEST_INTERVAL_MINUTES` (default: 15)
- `PING_COUNT` controls how many ICMP packets are sent per ping run (default: 4)

### Interfaces
The script uses `eth0` and `wlan0` by default. Override with:
```bash
export PING_INTERFACES="eth0,wlan0"
```
*(Note: speedtests and downloads rely on the interface IP being assigned.)*

### HTTP load tests (Locust)
- Configure targets with `HTTP_TEST_URLS` (comma separated, full URLs).
- Concurrency and pacing: `HTTP_LOCUST_USERS` (default: 20 for Pi), `HTTP_LOCUST_SPAWN_RATE` (default: 10), `HTTP_TEST_DURATION_SECONDS` (default: 30).
- Runs are scheduled per URL and interface and staggered evenly within `HTTP_TEST_INTERVAL_MINUTES` to avoid overlapping load; the window is divided by (`number of URLs` × `number of interfaces`).
- Each run executes in headless mode per interface and records request totals, failure ratio, avg/p95 latency to Influx (`http_load_test`).
- Ensure `locust` is installed via `pip install -r requirements.txt`.

## InfluxDB + Grafana with Docker
Launch InfluxDB and Grafana locally:
```bash
docker compose up -d
```
All required configuration lives in `.env` (see `.env.example` for defaults) and is read by docker-compose.
Grafana will be available at `http://localhost:3000` and InfluxDB at `http://localhost:8086`.

## Grafana Data Source
Add an InfluxDB data source in Grafana:
- URL: `http://influxdb:8086` (if Grafana runs via Docker) or `http://<pi-ip>:8086` if external
- Organization: `wan-monitor`
- Bucket: `wan-monitor`
- Token: value of `INFLUXDB_TOKEN`

The script writes the following measurements:
- `ping_latency` (`latency_ms` field; `interface`, `host` tags)
- `speedtest` (`download_mbps`, `upload_mbps` fields; `interface` tag)
- `download_test` (`bandwidth_mbps`, `file_size_bytes`, `duration_seconds` fields; `interface`, `file` tags)
- `http_load_test` (`requests`, `fail_ratio`, `avg_ms`, `p95_ms` fields; `interface`, `target`, `method` tags)

## Notes for Raspberry Pi
- The Speedtest CLI is installed via `pip install -r requirements.txt` (version pinned in `requirements.txt`).
- The download tests use `wget` with the interface-bound IP (`--bind-address`) to ensure traffic uses the selected interface.
- Make sure the specified test files exist at `DOWNLOAD_BASE_URL` and are reachable from both interfaces.
- If you see CPU warnings from Locust on a Pi, lower `HTTP_LOCUST_USERS`/`HTTP_LOCUST_SPAWN_RATE` in `.env`.
