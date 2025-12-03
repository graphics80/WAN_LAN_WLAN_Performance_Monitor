import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List

import requests
from apscheduler.schedulers.gevent import GeventScheduler

from monitor_app.config import AppConfig
from monitor_app.metrics import write_metric
from monitor_app.net_utils import get_interface_ip


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


def _collect_stats(durations_ms: List[float], failures: int) -> Dict[str, float]:
    if not durations_ms:
        return {"requests": 0.0, "fail_ratio": 1.0 if failures else 0.0, "avg_ms": 0.0, "p95_ms": 0.0}
    durations_ms.sort()
    total_req = len(durations_ms) + failures
    avg = sum(durations_ms) / len(durations_ms)
    idx = min(len(durations_ms) - 1, int(0.95 * len(durations_ms)))
    p95 = durations_ms[idx]
    return {
        "requests": float(total_req),
        "fail_ratio": failures / total_req if total_req else 0.0,
        "avg_ms": avg,
        "p95_ms": p95,
    }


def run_http_load_for_target(interface: str, url: str, config: AppConfig) -> List[Dict[str, float]]:
    """Run a lightweight HTTP load using threads for a single URL/interface and return stats."""
    source_ip = get_interface_ip(interface)
    if not source_ip:
        logging.warning("No IP found for interface %s, skipping HTTP load test", interface)
        return []

    session = requests.Session()
    bind_http_session_to_source(session, source_ip)

    durations: List[float] = []
    failures = 0
    deadline = time.monotonic() + config.http_test_duration_seconds

    def worker() -> None:
        nonlocal failures
        start = time.perf_counter()
        try:
            resp = session.get(url, timeout=10)
            elapsed_ms = (time.perf_counter() - start) * 1000
            if resp.status_code < 400:
                durations.append(elapsed_ms)
            else:
                failures += 1
        except Exception:
            failures += 1

    with ThreadPoolExecutor(max_workers=config.http_locust_users) as executor:
        futures = []
        while time.monotonic() < deadline:
            futures.append(executor.submit(worker))
        for _ in as_completed(futures):
            pass

    stats = _collect_stats(durations, failures)
    return [
        {
            "target": url,
            "method": "GET",
            **stats,
        }
    ]


def run_http_load_job(interface: str, url: str, client, config: AppConfig) -> None:
    """Execute load test and write results to Influx."""
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
    """Schedule per-URL, per-interface HTTP load tests staggered within the interval."""
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
