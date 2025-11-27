# WAN / LAN / WLAN Performance Monitor

Python script for a Raspberry Pi that measures network performance via the `eth0` and `wlan0` interfaces and stores the results in InfluxDB, ready to be visualized in Grafana.

## Features
- Ping latency for multiple targets every minute (per interface)
- Speedtest download/upload every 60 minutes (per interface) using the Speedtest CLI
- Download-based bandwidth checks every 5 minutes for 5 MB, 50 MB, and 80 MB files (per interface)
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
5. Start the monitor locally from the activated venv:
   ```bash
   python monitor.py
   ```

### Scheduling intervals
- `PING_INTERVAL_MINUTES` (default: 1)
- `SPEEDTEST_INTERVAL_MINUTES` (default: 60)
- `DOWNLOAD_INTERVAL_MINUTES` (default: 5)
- `PING_COUNT` controls how many ICMP packets are sent per ping run (default: 4)

### Interfaces
The script uses `eth0` and `wlan0` by default. Override with:
```bash
export PING_INTERFACES="eth0,wlan0"
```
*(Note: speedtests and downloads rely on the interface IP being assigned.)*

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

## Notes for Raspberry Pi
- The Speedtest CLI is installed via `pip install -r requirements.txt` (version pinned in `requirements.txt`).
- The download tests use `wget` with the interface-bound IP (`--bind-address`) to ensure traffic uses the selected interface.
- Make sure the specified test files exist at `DOWNLOAD_BASE_URL` and are reachable from both interfaces.
