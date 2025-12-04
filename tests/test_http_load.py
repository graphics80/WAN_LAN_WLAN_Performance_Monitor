from datetime import datetime

from monitor_app.config import AppConfig
from monitor_app.tasks import http_load


def test_run_http_load_job_writes(monkeypatch):
    cfg = AppConfig(ping_interfaces=["eth0"])
    sample_stats = [
        {"target": "u1", "method": "GET", "requests": 10.0, "fail_ratio": 0.1, "avg_ms": 5.0, "p95_ms": 8.0}
    ]

    monkeypatch.setattr(http_load, "run_http_load_for_target", lambda iface, url, c: sample_stats)
    calls = []

    def fake_write(client, config, measurement, tags, fields):
        calls.append((measurement, tags, fields))

    monkeypatch.setattr(http_load, "write_metric", fake_write)
    http_load.run_http_load_job("eth0", "https://example.com", None, cfg)
    assert calls[0][0] == "http_load_test"
    assert calls[0][1]["interface"] == "eth0"
    assert calls[0][1]["target"] == "u1"


def test_schedule_http_load_jobs_offsets(monkeypatch, dummy_scheduler):
    cfg = AppConfig(ping_interfaces=["eth0", "wlan0"], http_test_urls=["u1", "u2"], http_test_interval_minutes=20)
    monkeypatch.setattr(http_load, "run_http_load_job", lambda i, u, client, c: None)
    http_load.schedule_http_load_jobs(dummy_scheduler, None, cfg)
    assert len(dummy_scheduler.jobs) == 4
    ids = {job["id"] for job in dummy_scheduler.jobs}
    assert ids == {"http_load_eth0_0", "http_load_eth0_1", "http_load_wlan0_0", "http_load_wlan0_1"}
    slot = cfg.http_test_interval_minutes / 4
    times = sorted(job["next_run_time"] for job in dummy_scheduler.jobs)
    offsets = [(t - times[0]).total_seconds() / 60 for t in times]
    for idx, off in enumerate(offsets):
        assert abs(off - slot * idx) < 0.2
