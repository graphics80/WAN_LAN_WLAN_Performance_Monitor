import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass
class AppConfig:
    """Runtime configuration loaded from environment variables (and optionally .env)."""

    enable_ping: bool = True
    enable_speedtest: bool = True
    enable_download_tests: bool = True
    enable_http_tests: bool = True
    ping_targets: List[str] = field(default_factory=lambda: ["www.google.ch", "wiki.bzz.ch"])
    ping_interfaces: List[str] = field(default_factory=lambda: ["eth0", "wlan0"])
    ping_count: int = 4
    ping_interval_seconds: int = 10
    ping_max_instances: int = 2
    speedtest_interval_minutes: int = 60
    download_interval_minutes: int = 5
    download_max_instances: int = 3
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

        def parse_bool(env_name: str, fallback: bool) -> bool:
            raw = os.getenv(env_name)
            if raw is None:
                return fallback
            value = raw.strip().lower()
            if value in ("1", "true", "yes", "on"):
                return True
            if value in ("0", "false", "no", "off"):
                return False
            logging.warning("Invalid value for %s=%s, using default %s", env_name, raw, fallback)
            return fallback

        ping_interval_seconds = parse_int("PING_INTERVAL_SECONDS", 10)
        if "PING_INTERVAL_SECONDS" not in os.environ and "PING_INTERVAL_MINUTES" in os.environ:
            # Support the previous minutes-based setting to keep existing .env files working.
            minutes_value = parse_int("PING_INTERVAL_MINUTES", 1)
            ping_interval_seconds = minutes_value * 60
            logging.info(
                "PING_INTERVAL_MINUTES is deprecated; please switch to PING_INTERVAL_SECONDS (currently %s seconds)",
                ping_interval_seconds,
            )
        elif ping_interval_seconds <= 0:
            logging.warning("PING_INTERVAL_SECONDS must be positive, using default of 10")
            ping_interval_seconds = 10

        return AppConfig(
            enable_ping=parse_bool("ENABLE_PING", True),
            enable_speedtest=parse_bool("ENABLE_SPEEDTEST", True),
            enable_download_tests=parse_bool("ENABLE_DOWNLOAD_TESTS", True),
            enable_http_tests=parse_bool("ENABLE_HTTP_TESTS", True),
            ping_targets=parse_list("PING_TARGETS", default_ping_targets),
            ping_interfaces=parse_list("PING_INTERFACES", default_ping_interfaces),
            ping_count=parse_int("PING_COUNT", 4),
            ping_interval_seconds=ping_interval_seconds,
            ping_max_instances=parse_int("PING_MAX_INSTANCES", 2),
            speedtest_interval_minutes=parse_int("SPEEDTEST_INTERVAL_MINUTES", 60),
            download_interval_minutes=parse_int("DOWNLOAD_INTERVAL_MINUTES", 5),
            download_max_instances=parse_int("DOWNLOAD_MAX_INSTANCES", 3),
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
    """Configure root logger for the monitor."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


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
