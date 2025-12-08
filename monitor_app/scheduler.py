import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from monitor_app.config import AppConfig
from monitor_app.tasks.download import run_download_tests
from monitor_app.tasks.http_load import schedule_http_load_jobs
from monitor_app.tasks.ping import run_ping_checks
from monitor_app.tasks.speedtest import run_speedtests


def start_scheduler(client, config: AppConfig) -> BackgroundScheduler:
    """Set up recurring jobs for ping, speedtest, downloads, and HTTP load tests."""
    scheduler = BackgroundScheduler()
    logging.info("Scheduling ping checks every %s second(s)", config.ping_interval_seconds)
    scheduler.add_job(
        lambda: run_ping_checks(client, config),
        "interval",
        seconds=config.ping_interval_seconds,
        next_run_time=datetime.now(),
        id="ping_checks",
        name="ping_checks",
    )

    logging.info("Scheduling speedtests every %s minute(s)", config.speedtest_interval_minutes)
    scheduler.add_job(
        lambda: run_speedtests(client, config),
        "interval",
        minutes=config.speedtest_interval_minutes,
        next_run_time=datetime.now(),
        id="speedtests",
        name="speedtests",
    )

    logging.info("Scheduling download tests every %s minute(s)", config.download_interval_minutes)
    scheduler.add_job(
        lambda: run_download_tests(client, config),
        "interval",
        minutes=config.download_interval_minutes,
        next_run_time=datetime.now(),
        id="download_tests",
        name="download_tests",
        max_instances=config.download_max_instances,
    )

    schedule_http_load_jobs(scheduler, client, config)
    scheduler.start()
    return scheduler
