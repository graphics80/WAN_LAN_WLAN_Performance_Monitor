from types import SimpleNamespace

from monitor_app.config import AppConfig
from monitor_app.tasks import ping


def test_parse_ping_output():
    sample = "rtt min/avg/max/mdev = 1.000/2.500/3.000/0.500 ms"
    assert ping.parse_ping_output(sample) == 2.5


def test_ping_host_success(monkeypatch):
    def fake_run(cmd, capture_output, text):
        return SimpleNamespace(returncode=0, stdout="round-trip min/avg/max = 1/2/3/0\n", stderr="")

    monkeypatch.setattr(ping.subprocess, "run", fake_run)
    latency = ping.ping_host("example.com", "eth0", 1)
    assert latency == 2.0


def test_run_ping_checks_writes(monkeypatch):
    cfg = AppConfig(ping_targets=["h1"], ping_interfaces=["eth0"])

    def fake_ping_host(host, interface, count):
        return 5.0

    calls = []

    def fake_write(client, config, measurement, tags, fields):
        calls.append((measurement, tags, fields))

    monkeypatch.setattr(ping, "ping_host", fake_ping_host)
    monkeypatch.setattr(ping, "write_metric", fake_write)
    ping.run_ping_checks(None, cfg)
    assert calls[0][0] == "ping_latency"
    assert calls[0][1] == {"interface": "eth0", "host": "h1"}
    assert calls[0][2]["latency_ms"] == 5.0
