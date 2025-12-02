import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import netifaces
from apscheduler.schedulers.background import BackgroundScheduler
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from influxdb_client.rest import ApiException


@dataclass
class AppConfig:
    ping_targets: List[str] = field(default_factory=lambda: ["www.google.ch", "wiki.bzz.ch"])
    ping_interfaces: List[str] = field(default_factory=lambda: ["eth0", "wlan0"])
    ping_count: int = 4
    ping_interval_minutes: int = 1
    speedtest_interval_minutes: int = 60
    download_interval_minutes: int = 5
    download_base_url: str = "https://example.com/test-files"
    download_files: List[str] = field(default_factory=lambda: ["5mb.zip", "50mb.zip", "80mb.zip"])

    influx_url: str = "http://localhost:8086"
    influx_token: str = ""
    influx_org: str = "wan-monitor"
    influx_bucket: str = "wan-monitor"

    @staticmethod
    def from_env() -> "AppConfig":
        default_ping_targets = ["www.google.ch", "wiki.bzz.ch"]
        default_ping_interfaces = ["eth0", "wlan0"]
        default_download_files = ["5mb.zip", "50mb.zip", "80mb.zip"]

        def parse_list(env_name: str, fallback: List[str]) -> List[str]:
            raw = os.getenv(env_name)
            if not raw:
                return fallback
            parsed = [item.strip() for item in raw.split(",") if item.strip()]
            return parsed if parsed else fallback

        def parse_int(env_name: str, fallback: int) -> int:
            raw = os.getenv(env_name)
            if raw is None:
                return fallback
            try:
                return int(raw)
            except ValueError:
                logging.warning("Invalid value for %s=%s, using default %s", env_name, raw, fallback)
                return fallback

        return AppConfig(
            ping_targets=parse_list("PING_TARGETS", default_ping_targets),
            ping_interfaces=parse_list("PING_INTERFACES", default_ping_interfaces),
            ping_count=parse_int("PING_COUNT", 4),
            ping_interval_minutes=parse_int("PING_INTERVAL_MINUTES", 1),
            speedtest_interval_minutes=parse_int("SPEEDTEST_INTERVAL_MINUTES", 60),
            download_interval_minutes=parse_int("DOWNLOAD_INTERVAL_MINUTES", 5),
            download_base_url=os.getenv("DOWNLOAD_BASE_URL", "https://example.com/test-files"),
            download_files=parse_list("DOWNLOAD_FILES", default_download_files),
            influx_url=os.getenv("INFLUX_URL", "http://localhost:8086"),
            influx_token=os.getenv("INFLUX_TOKEN") or os.getenv("INFLUXDB_TOKEN", ""),
            influx_org=os.getenv("INFLUX_ORG", "wan-monitor"),
            influx_bucket=os.getenv("INFLUX_BUCKET", "wan-monitor"),
        )


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def load_env_from_file(env_path: str = ".env") -> None:
    """
    Populate os.environ using a local .env file when environment variables are not already set.
    Existing environment values take precedence over file entries.
    """
    path = Path(env_path)
    if not path.exists():
        return

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key and key not in os.environ:
            os.environ[key] = value


def get_interface_ip(interface: str) -> Optional[str]:
    try:
        iface_info = netifaces.ifaddresses(interface)
        inet_info = iface_info.get(netifaces.AF_INET)
        if not inet_info:
            return None
        return inet_info[0].get("addr")
    except ValueError:
        return None


def create_influx_client(config: AppConfig) -> InfluxDBClient:
    return InfluxDBClient(url=config.influx_url, token=config.influx_token, org=config.influx_org)


def write_metric(client: InfluxDBClient, config: AppConfig, measurement: str, tags: Dict[str, str], fields: Dict[str, float]) -> None:
    if not config.influx_token:
        logging.warning("Skipping InfluxDB write for %s: INFLUX_TOKEN not set", measurement)
        return

    point = Point(measurement)
    for key, value in tags.items():
        point = point.tag(key, value)
    for key, value in fields.items():
        point = point.field(key, value)

    write_api = client.write_api(write_options=SYNCHRONOUS)
    try:
        write_api.write(bucket=config.influx_bucket, org=config.influx_org, record=point)
    except ApiException as exc:
        logging.error("Failed to write %s to InfluxDB: %s", measurement, exc)
    except Exception:
        logging.exception("Unexpected error while writing %s to InfluxDB", measurement)


def parse_ping_output(output: str) -> Optional[float]:
    for line in output.splitlines():
        if "rtt min/avg/max" in line or "round-trip min/avg/max" in line:
            parts = line.split("=")
            if len(parts) < 2:
                continue
            stats_part = parts[1].strip().split("/")
            if len(stats_part) >= 2:
                try:
                    return float(stats_part[1])
                except ValueError:
                    return None
    return None


def ping_host(host: str, interface: str, count: int) -> Optional[float]:
    cmd = ["ping", "-I", interface, "-c", str(count), "-q", host]
    logging.debug("Running ping: %s", shlex.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.warning("Ping failed for %s on %s: %s", host, interface, result.stderr.strip())
        return None
    latency = parse_ping_output(result.stdout)
    if latency is None:
        logging.warning("Could not parse ping output for %s on %s", host, interface)
    return latency


def run_ping_checks(client: InfluxDBClient, config: AppConfig) -> None:
    logging.info("Starting ping checks")
    for interface in config.ping_interfaces:
        for host in config.ping_targets:
            latency = ping_host(host, interface, config.ping_count)
            if latency is None:
                continue
            write_metric(
                client,
                config,
                "ping_latency",
                {"interface": interface, "host": host},
                {"latency_ms": latency},
            )
            logging.info("Ping %s via %s: %.2f ms", host, interface, latency)


def run_speedtest_for_interface(interface: str) -> Optional[Dict[str, float]]:
    source_ip = get_interface_ip(interface)
    if not source_ip:
        logging.warning("No IP found for interface %s, skipping speedtest", interface)
        return None

    cmd = [
        "speedtest",
        "--json",
        "--secure",
        "--source",
        source_ip,
    ]
    logging.debug("Running speedtest: %s", shlex.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.warning("Speedtest failed on %s: %s", interface, result.stderr.strip())
        return None

    try:
        payload = json.loads(result.stdout)
        download_bps = payload.get("download")
        upload_bps = payload.get("upload")
        ping_ms = payload.get("ping")
        if download_bps is None or upload_bps is None:
            logging.warning("Unexpected speedtest output on %s", interface)
            return None
        return {
            # speedtest-cli reports bits per second
            "download_mbps": download_bps / 1_000_000,
            "upload_mbps": upload_bps / 1_000_000,
            "ping_ms": float(ping_ms) if ping_ms is not None else None,
        }
    except json.JSONDecodeError:
        logging.warning("Could not decode speedtest output on %s", interface)
        return None


def run_speedtests(client: InfluxDBClient, config: AppConfig) -> None:
    logging.info("Starting speedtests")
    for interface in config.ping_interfaces:
        metrics = run_speedtest_for_interface(interface)
        if not metrics:
            continue
        if metrics.get("ping_ms") is None:
            metrics.pop("ping_ms", None)
        write_metric(
            client,
            config,
            "speedtest",
            {"interface": interface},
            metrics,
        )
        logging.info(
            "Speedtest via %s: %.2f Mbps down / %.2f Mbps up",
            interface,
            metrics["download_mbps"],
            metrics["upload_mbps"],
        )


def download_file(url: str, interface: str) -> Optional[Dict[str, float]]:
    source_ip = get_interface_ip(interface)
    if not source_ip:
        logging.warning("No IP found for interface %s, skipping download test", interface)
        return None

    with tempfile.TemporaryDirectory() as tmpdir:
        target_path = Path(tmpdir) / Path(url).name
        cmd = [
            "wget",
            f"--bind-address={source_ip}",
            "-O",
            str(target_path),
            url,
            "--quiet",
        ]
        start = time.perf_counter()
        result = subprocess.run(cmd, capture_output=True, text=True)
        elapsed = time.perf_counter() - start

        if result.returncode != 0:
            logging.warning("Download failed for %s on %s: %s", url, interface, result.stderr.strip())
            return None

        try:
            size_bytes = target_path.stat().st_size
        except FileNotFoundError:
            logging.warning("Downloaded file missing for %s on %s", url, interface)
            return None

        if elapsed == 0:
            logging.warning("Elapsed time is zero for %s on %s", url, interface)
            return None

        bandwidth_mbps = (size_bytes * 8 / 1_000_000) / elapsed
        return {
            "bandwidth_mbps": bandwidth_mbps,
            "file_size_bytes": float(size_bytes),
            "duration_seconds": elapsed,
        }


def run_download_tests(client: InfluxDBClient, config: AppConfig) -> None:
    logging.info("Starting download tests")
    for interface in config.ping_interfaces:
        for filename in config.download_files:
            url = f"{config.download_base_url.rstrip('/')}/{filename}"
            metrics = download_file(url, interface)
            if not metrics:
                continue
            write_metric(
                client,
                config,
                "download_test",
                {"interface": interface, "file": filename},
                metrics,
            )
            logging.info(
                "Download via %s %s: %.2f Mbps (%.2fs)",
                interface,
                filename,
                metrics["bandwidth_mbps"],
                metrics["duration_seconds"],
            )


def start_scheduler(client: InfluxDBClient, config: AppConfig) -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(lambda: run_ping_checks(client, config), "interval", minutes=config.ping_interval_minutes, next_run_time=datetime.now())
    scheduler.add_job(lambda: run_speedtests(client, config), "interval", minutes=config.speedtest_interval_minutes, next_run_time=datetime.now())
    scheduler.add_job(lambda: run_download_tests(client, config), "interval", minutes=config.download_interval_minutes, next_run_time=datetime.now())
    scheduler.start()
    return scheduler


def main() -> None:
    configure_logging()
    load_env_from_file()
    config = AppConfig.from_env()
    client = create_influx_client(config)

    logging.info("Starting WAN/LAN/WLAN Performance Monitor")
    scheduler = start_scheduler(client, config)

    try:
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        logging.info("Shutting down...")
        scheduler.shutdown(wait=False)


if __name__ == "__main__":
    main()
