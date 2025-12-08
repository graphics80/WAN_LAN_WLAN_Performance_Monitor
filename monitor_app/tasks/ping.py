import logging
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from monitor_app.config import AppConfig
from monitor_app.metrics import write_metric


def parse_ping_output(output: str) -> Optional[float]:
    """Extract average latency from ping output."""
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
    """Run ping bound to an interface and return avg latency in ms."""
    cmd = ["ping", "-I", interface, "-c", str(count), "-q", host]
    logging.debug("Running ping: %s", shlex.join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logging.warning("Ping failed for %s on %s: %s", host, interface, result.stderr.strip())
        return None
    return parse_ping_output(result.stdout)


def run_ping_checks(client, config: AppConfig) -> None:
    """Ping all configured hosts per interface and write metrics."""
    logging.info("Starting ping checks")
    tasks = [(interface, host) for interface in config.ping_interfaces for host in config.ping_targets]
    if not tasks:
        return

    with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        future_map = {
            executor.submit(ping_host, host, interface, config.ping_count): (interface, host) for interface, host in tasks
        }
        for future in as_completed(future_map):
            interface, host = future_map[future]
            try:
                latency = future.result()
            except Exception as exc:  # pragma: no cover - defensive logging
                logging.warning("Ping failed for %s on %s: %s", host, interface, exc)
                continue
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
