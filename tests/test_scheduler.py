from monitor_app.config import AppConfig
from monitor_app import scheduler


def test_start_scheduler_adds_jobs(monkeypatch):
    cfg = AppConfig(ping_interfaces=["eth0"], http_test_urls=["u1"], http_test_interval_minutes=10)

    added = []

    class DummyScheduler:
        def add_job(self, func, trigger, **kwargs):
            added.append(kwargs["id"])

        def start(self):
            return

    monkeypatch.setattr(scheduler, "BackgroundScheduler", lambda: DummyScheduler())
    sch = scheduler.start_scheduler(None, cfg)
    assert {"ping_checks", "speedtests", "download_tests", "http_load_eth0_0"}.issubset(set(added))


def test_start_scheduler_skips_disabled(monkeypatch):
    cfg = AppConfig(
        enable_ping=False,
        enable_speedtest=False,
        enable_download_tests=False,
        enable_http_tests=False,
        ping_interfaces=["eth0"],
        http_test_urls=["u1"],
        http_test_interval_minutes=10,
    )

    added = []

    class DummyScheduler:
        def add_job(self, func, trigger, **kwargs):
            added.append(kwargs["id"])

        def start(self):
            return

    monkeypatch.setattr(scheduler, "BackgroundScheduler", lambda: DummyScheduler())
    scheduler.start_scheduler(None, cfg)
    assert added == []


def test_ping_job_respects_max_instances(monkeypatch):
    cfg = AppConfig(ping_interfaces=["eth0"], ping_max_instances=4)

    jobs = []

    class DummyScheduler:
        def add_job(self, func, trigger, **kwargs):
            jobs.append(kwargs)

        def start(self):
            return

    monkeypatch.setattr(scheduler, "BackgroundScheduler", lambda: DummyScheduler())
    scheduler.start_scheduler(None, cfg)

    ping_jobs = [job for job in jobs if job["id"] == "ping_checks"]
    assert ping_jobs, "Ping job should be scheduled"
    assert ping_jobs[0]["max_instances"] == 4
