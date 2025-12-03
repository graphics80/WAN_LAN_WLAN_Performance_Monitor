import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

from monitor_app.config import AppConfig
from monitor_app.metrics import write_metric
from monitor_app.net_utils import get_interface_ip


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


def run_download_tests(client, config: AppConfig) -> None:
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
