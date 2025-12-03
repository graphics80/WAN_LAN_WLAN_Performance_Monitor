import logging
import shlex
import subprocess
from typing import Optional

from monitor_app.config import AppConfig
from monitor_app.metrics import write_metric
from monitor_app.net_utils import get_interface_ip  # noqa: F401 (kept for symmetry)


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


def run_ping_checks(client, config: AppConfig) -> None:
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
