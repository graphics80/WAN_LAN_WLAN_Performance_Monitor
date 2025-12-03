from pathlib import Path
from types import SimpleNamespace

from monitor_app.config import AppConfig
from monitor_app.tasks import download_tasks


def test_download_file(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(download_tasks, "get_interface_ip", lambda iface: "1.2.3.4")

    def fake_run(cmd, capture_output, text):
        # Locate output path after "-O"
        out_path = Path(cmd[cmd.index("-O") + 1])
        out_path.write_text("data")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(download_tasks.subprocess, "run", fake_run)
    metrics = download_tasks.download_file("https://example.com/file", "eth0")
    assert metrics is not None
    assert metrics["bandwidth_mbps"] > 0


def test_run_download_tests_writes(monkeypatch):
    cfg = AppConfig(ping_interfaces=["eth0"], download_files=["f1"])
    monkeypatch.setattr(download_tasks, "download_file", lambda url, iface: {"bandwidth_mbps": 10, "file_size_bytes": 100, "duration_seconds": 1})

    calls = []

    def fake_write(client, config, measurement, tags, fields):
        calls.append((measurement, tags, fields))

    monkeypatch.setattr(download_tasks, "write_metric", fake_write)
    download_tasks.run_download_tests(None, cfg)
    assert calls[0][0] == "download_test"
    assert calls[0][1]["interface"] == "eth0"
