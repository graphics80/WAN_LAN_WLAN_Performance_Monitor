import logging
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, Optional

from monitor_app.config import AppConfig
from monitor_app.metrics import write_metric
from monitor_app.net import get_interface_ip


def download_file(url: str, interface: str) -> Optional[Dict[str, float]]:
    """Download a file via a specific interface and return bandwidth metrics."""
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
    """Run download tests per interface/file and write metrics."""
    logging.info("Starting download tests")

    def resolve_url(entry: str) -> Optional[tuple[str, str]]:
        """
        Return (label, url) for a download entry.
        Supports:
        - full URLs (label derived from path)
        - "label|url" entries to override label while using an absolute URL
        - relative filenames combined with download_base_url
        """
        label = entry
        raw = entry

        if "|" in entry:
            parts = entry.split("|", 1)
            label = parts[0].strip() or label
            raw = parts[1].strip()

        if not raw:
            return None

        if raw.startswith(("http://", "https://")):
            url = raw
            # Use last path segment as label if none was provided.
            label = label or Path(url).name or url
        else:
            url = f"{config.download_base_url.rstrip('/')}/{raw}"
            label = label or raw

        return label, url

    for interface in config.ping_interfaces:
        for entry in config.download_files:
            resolved = resolve_url(entry)
            if not resolved:
                logging.warning("Invalid download entry '%s', skipping", entry)
                continue
            label, url = resolved
            metrics = download_file(url, interface)
            if not metrics:
                continue
            write_metric(
                client,
                config,
                "download_test",
                {"interface": interface, "file": label},
                metrics,
            )
            logging.info(
                "Download via %s %s: %.2f Mbps (%.2fs)",
                interface,
                label,
                metrics["bandwidth_mbps"],
                metrics["duration_seconds"],
            )
