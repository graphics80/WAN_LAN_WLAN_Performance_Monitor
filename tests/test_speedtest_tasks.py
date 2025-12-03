from types import SimpleNamespace

from monitor_app.config import AppConfig
from monitor_app.tasks import speedtest_tasks


def test_run_speedtest_for_interface(monkeypatch):
    monkeypatch.setattr(speedtest_tasks, "get_interface_ip", lambda iface: "1.2.3.4")

    def fake_run(cmd, capture_output, text):
        payload = '{"download": 1000000, "upload": 2000000, "ping": 5}'
        return SimpleNamespace(returncode=0, stdout=payload, stderr="")

    monkeypatch.setattr(speedtest_tasks.subprocess, "run", fake_run)
    metrics = speedtest_tasks.run_speedtest_for_interface("eth0")
    assert metrics["download_mbps"] == 1.0
    assert metrics["upload_mbps"] == 2.0
    assert metrics["ping_ms"] == 5.0


def test_run_speedtests_writes(monkeypatch):
    cfg = AppConfig(ping_interfaces=["eth0"])
    monkeypatch.setattr(speedtest_tasks, "run_speedtest_for_interface", lambda iface: {"download_mbps": 1, "upload_mbps": 2, "ping_ms": 3})

    calls = []

    def fake_write(client, config, measurement, tags, fields):
        calls.append((measurement, tags, fields))

    monkeypatch.setattr(speedtest_tasks, "write_metric", fake_write)
    speedtest_tasks.run_speedtests(None, cfg)
    assert calls[0][0] == "speedtest"
    assert calls[0][1]["interface"] == "eth0"
    assert calls[0][2]["download_mbps"] == 1
