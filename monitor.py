import json
import logging
import os
import shlex
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from locust import HttpUser, constant, task
from locust.env import Environment
from locust.runners import LocalRunner
import gevent
import netifaces
import requests
from apscheduler.schedulers.gevent import GeventScheduler
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
    http_test_urls: List[str] = field(default_factory=lambda: ["https://www.google.com"])
    http_test_interval_minutes: int = 15
    http_locust_users: int = 100
    http_locust_spawn_rate: int = 100
    http_test_duration_seconds: int = 30

    influx_url: str = "http://localhost:8086"
    influx_token: str = ""
    influx_org: str = "wan-monitor"
    influx_bucket: str = "wan-monitor"

    @staticmethod
    def from_env() -> "AppConfig":
        default_ping_targets = ["www.google.ch", "wiki.bzz.ch"]
        default_ping_interfaces = ["eth0", "wlan0"]
        default_download_files = ["5mb.zip", "50mb.zip", "80mb.zip"]
        default_http_test_urls = ["https://www.google.com"]

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
            http_test_urls=parse_list("HTTP_TEST_URLS", default_http_test_urls),
            http_test_interval_minutes=parse_int("HTTP_TEST_INTERVAL_MINUTES", 15),
            http_locust_users=parse_int("HTTP_LOCUST_USERS", 100),
            http_locust_spawn_rate=parse_int("HTTP_LOCUST_SPAWN_RATE", 100),
            http_test_duration_seconds=parse_int("HTTP_TEST_DURATION_SECONDS", 30),
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


def bind_http_session_to_source(http_session: "requests.sessions.Session", source_ip: str) -> None:
    """
    Ensure HTTP requests originate from the given source IP by mounting adapters with a bound source_address.
    """
    session = getattr(http_session, "_session", None) or getattr(http_session, "session", None) or http_session
    adapter = requests.adapters.HTTPAdapter(pool_connections=200, pool_maxsize=200)
    adapter.init_poolmanager(
        connections=adapter._pool_connections,
        maxsize=adapter._pool_maxsize,
        block=adapter._pool_block,
        source_address=(source_ip, 0),
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)


def make_http_user(urls: List[str], source_ip: str) -> type:
    class InterfaceHttpUser(HttpUser):  # type: ignore[misc]
        host = ""
        wait_time = constant(0)
        abstract = True

        def on_start(self) -> None:
            bind_http_session_to_source(self.client, source_ip)

        @task
        def hit_targets(self) -> None:
            for url in urls:
                self.client.get(url, name=url, timeout=15)

    InterfaceHttpUser.__name__ = f"HttpUser_{source_ip.replace('.', '_')}"
    return InterfaceHttpUser


def run_http_load_for_target(interface: str, url: str, config: AppConfig) -> List[Dict[str, float]]:
    source_ip = get_interface_ip(interface)
    if not source_ip:
        logging.warning("No IP found for interface %s, skipping HTTP load test", interface)
        return []

    user_class = make_http_user([url], source_ip)
    env = Environment(user_classes=[user_class])
    runner: LocalRunner = env.create_local_runner()

    logging.info(
        "Starting HTTP load test for %s via %s (%s users for %ss)",
        url,
        interface,
        config.http_locust_users,
        config.http_test_duration_seconds,
    )
    try:
        runner.start(user_count=config.http_locust_users, spawn_rate=config.http_locust_spawn_rate)
        gevent.sleep(config.http_test_duration_seconds)
    finally:
        runner.quit()
        runner.greenlet.join()

    results: List[Dict[str, float]] = []
    for (method, name), stat in env.stats.entries.items():
        if stat.num_requests == 0:
            continue
        results.append(
            {
                "target": name,
                "method": method,
                "requests": float(stat.num_requests),
                "fail_ratio": float(stat.fail_ratio),
                "avg_ms": float(stat.avg_response_time),
                "p95_ms": float(stat.get_response_time_percentile(0.95)),
            }
        )

    total = env.stats.total
    if total.num_requests:
        results.append(
            {
                "target": "all",
                "method": "ALL",
                "requests": float(total.num_requests),
                "fail_ratio": float(total.fail_ratio),
                "avg_ms": float(total.avg_response_time),
                "p95_ms": float(total.get_response_time_percentile(0.95)),
            }
        )

    return results


def run_http_load_job(interface: str, url: str, client: InfluxDBClient, config: AppConfig) -> None:
    stats = run_http_load_for_target(interface, url, config)
    for stat in stats:
        fields = {
            "requests": stat["requests"],
            "fail_ratio": stat["fail_ratio"],
            "avg_ms": stat["avg_ms"],
            "p95_ms": stat["p95_ms"],
        }
        write_metric(
            client,
            config,
            "http_load_test",
            {"interface": interface, "target": stat["target"], "method": stat["method"]},
            fields,
        )
        logging.info(
            "HTTP load via %s target %s: avg %.2f ms p95 %.2f ms, fail %.3f over %.0f requests",
            interface,
            stat["target"],
            stat["avg_ms"],
            stat["p95_ms"],
            stat["fail_ratio"],
            stat["requests"],
        )


def schedule_http_load_jobs(scheduler: GeventScheduler, client: InfluxDBClient, config: AppConfig) -> None:
    urls = config.http_test_urls
    if not urls:
        logging.info("No HTTP test URLs configured; skipping HTTP load scheduling")
        return

    slot_minutes = config.http_test_interval_minutes / max(1, len(urls))
    now = datetime.now()
    for interface in config.ping_interfaces:
        for idx, url in enumerate(urls):
            offset_minutes = slot_minutes * idx
            next_run = now + timedelta(minutes=offset_minutes)
            job_id = f"http_load_{interface}_{idx}"
            logging.info(
                "Scheduling HTTP load for %s via %s every %s min (offset %.2f min)",
                url,
                interface,
                config.http_test_interval_minutes,
                offset_minutes,
            )
            scheduler.add_job(
                lambda i=interface, u=url: run_http_load_job(i, u, client, config),
                "interval",
                minutes=config.http_test_interval_minutes,
                next_run_time=next_run,
                id=job_id,
                name=job_id,
            )


def start_scheduler(client: InfluxDBClient, config: AppConfig) -> GeventScheduler:
    scheduler = GeventScheduler()
    logging.info("Scheduling ping checks every %s minute(s)", config.ping_interval_minutes)
    scheduler.add_job(
        lambda: run_ping_checks(client, config),
        "interval",
        minutes=config.ping_interval_minutes,
        next_run_time=datetime.now(),
        id="ping_checks",
        name="ping_checks",
    )

    logging.info("Scheduling speedtests every %s minute(s)", config.speedtest_interval_minutes)
    scheduler.add_job(
        lambda: run_speedtests(client, config),
        "interval",
        minutes=config.speedtest_interval_minutes,
        next_run_time=datetime.now(),
        id="speedtests",
        name="speedtests",
    )

    logging.info("Scheduling download tests every %s minute(s)", config.download_interval_minutes)
    scheduler.add_job(
        lambda: run_download_tests(client, config),
        "interval",
        minutes=config.download_interval_minutes,
        next_run_time=datetime.now(),
        id="download_tests",
        name="download_tests",
    )

    schedule_http_load_jobs(scheduler, client, config)
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
