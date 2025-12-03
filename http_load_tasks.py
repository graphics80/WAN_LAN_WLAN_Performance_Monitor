import logging
from datetime import datetime, timedelta
from typing import Dict, List

import gevent
import requests
from apscheduler.schedulers.gevent import GeventScheduler
from locust import HttpUser, constant, task
from locust.env import Environment
from locust.runners import LocalRunner

from config import AppConfig
from metrics import write_metric
from net_utils import get_interface_ip


def bind_http_session_to_source(http_session: "requests.sessions.Session", source_ip: str) -> None:
    """
    Ensure HTTP requests originate from the given source IP by mounting adapters with a bound source_address.
    """
    session = getattr(http_session, "_session", None) or getattr(http_session, "session", None) or http_session
    adapter = requests.adapters.HTTPAdapter(pool_connections=200, pool_maxsize=200)
    adapter.init_poolmanager(
        connections=adapter._pool_connections,
        maxsize=adapter._pool_maxsize,
        block=adapter._pool_block,
        source_address=(source_ip, 0),
    )
    session.mount("http://", adapter)
    session.mount("https://", adapter)


def make_http_user(urls: List[str], source_ip: str) -> type:
    class InterfaceHttpUser(HttpUser):  # type: ignore[misc]
        host = ""
        wait_time = constant(0)
        abstract = True

        def on_start(self) -> None:
            bind_http_session_to_source(self.client, source_ip)

        @task
        def hit_targets(self) -> None:
            for url in urls:
                self.client.get(url, name=url, timeout=15)

    InterfaceHttpUser.__name__ = f"HttpUser_{source_ip.replace('.', '_')}"
    return InterfaceHttpUser


def run_http_load_for_target(interface: str, url: str, config: AppConfig) -> List[Dict[str, float]]:
    source_ip = get_interface_ip(interface)
    if not source_ip:
        logging.warning("No IP found for interface %s, skipping HTTP load test", interface)
        return []

    user_class = make_http_user([url], source_ip)
    env = Environment(user_classes=[user_class])
    runner: LocalRunner = env.create_local_runner()

    logging.info(
        "Starting HTTP load test for %s via %s (%s users for %ss)",
        url,
        interface,
        config.http_locust_users,
        config.http_test_duration_seconds,
    )
    try:
        runner.start(user_count=config.http_locust_users, spawn_rate=config.http_locust_spawn_rate)
        gevent.sleep(config.http_test_duration_seconds)
    finally:
        runner.quit()
        runner.greenlet.join()

    results: List[Dict[str, float]] = []
    for (method, name), stat in env.stats.entries.items():
        if stat.num_requests == 0:
            continue
        results.append(
            {
                "target": name,
                "method": method,
                "requests": float(stat.num_requests),
                "fail_ratio": float(stat.fail_ratio),
                "avg_ms": float(stat.avg_response_time),
                "p95_ms": float(stat.get_response_time_percentile(0.95)),
            }
        )

    total = env.stats.total
    if total.num_requests:
        results.append(
            {
                "target": "all",
                "method": "ALL",
                "requests": float(total.num_requests),
                "fail_ratio": float(total.fail_ratio),
                "avg_ms": float(total.avg_response_time),
                "p95_ms": float(total.get_response_time_percentile(0.95)),
            }
        )

    return results


def run_http_load_job(interface: str, url: str, client, config: AppConfig) -> None:
    stats = run_http_load_for_target(interface, url, config)
    for stat in stats:
        fields = {
            "requests": stat["requests"],
            "fail_ratio": stat["fail_ratio"],
            "avg_ms": stat["avg_ms"],
            "p95_ms": stat["p95_ms"],
        }
        write_metric(
            client,
            config,
            "http_load_test",
            {"interface": interface, "target": stat["target"], "method": stat["method"]},
            fields,
        )
        logging.info(
            "HTTP load via %s target %s: avg %.2f ms p95 %.2f ms, fail %.3f over %.0f requests",
            interface,
            stat["target"],
            stat["avg_ms"],
            stat["p95_ms"],
            stat["fail_ratio"],
            stat["requests"],
        )


def schedule_http_load_jobs(scheduler: GeventScheduler, client, config: AppConfig) -> None:
    urls = config.http_test_urls
    if not urls:
        logging.info("No HTTP test URLs configured; skipping HTTP load scheduling")
        return

    iface_count = max(1, len(config.ping_interfaces))
    total_jobs = max(1, len(urls) * iface_count)
    slot_minutes = config.http_test_interval_minutes / total_jobs
    now = datetime.now()

    for iface_idx, interface in enumerate(config.ping_interfaces):
        for url_idx, url in enumerate(urls):
            slot_index = iface_idx * len(urls) + url_idx
            offset_minutes = slot_minutes * slot_index
            next_run = now + timedelta(minutes=offset_minutes)
            job_id = f"http_load_{interface}_{url_idx}"
            logging.info(
                "Scheduling HTTP load for %s via %s every %s min (offset %.2f min)",
                url,
                interface,
                config.http_test_interval_minutes,
                offset_minutes,
            )
            scheduler.add_job(
                lambda i=interface, u=url: run_http_load_job(i, u, client, config),
                "interval",
                minutes=config.http_test_interval_minutes,
                next_run_time=next_run,
                id=job_id,
                name=job_id,
            )
