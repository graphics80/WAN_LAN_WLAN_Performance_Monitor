import json
import logging
import shlex
import subprocess
from typing import Dict, Optional

from monitor_app.config import AppConfig
from monitor_app.metrics import write_metric
from monitor_app.net_utils import get_interface_ip


def run_speedtest_for_interface(interface: str) -> Optional[Dict[str, float]]:
    """Execute speedtest-cli bound to an interface IP and return metrics in Mbps."""
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
            "download_mbps": download_bps / 1_000_000,
            "upload_mbps": upload_bps / 1_000_000,
            "ping_ms": float(ping_ms) if ping_ms is not None else None,
        }
    except json.JSONDecodeError:
        logging.warning("Could not decode speedtest output on %s", interface)
        return None


def run_speedtests(client, config: AppConfig) -> None:
    """Run speedtests per interface and write metrics."""
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
