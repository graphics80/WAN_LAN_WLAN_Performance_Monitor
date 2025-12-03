import os
import sys
import types
from pathlib import Path
from typing import List

import pytest

# Ensure project root on sys.path for imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def restore_env():
    """Restore environment variables after each test."""
    before = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(before)


class DummyScheduler:
    def __init__(self) -> None:
        self.jobs: List[dict] = []

    def add_job(self, func, trigger, minutes, next_run_time, id, name):
        self.jobs.append(
            {
                "func": func,
                "trigger": trigger,
                "minutes": minutes,
                "next_run_time": next_run_time,
                "id": id,
                "name": name,
            }
        )

    def start(self) -> None:
        return


class DummyRunner:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False
        self.user_count = 0
        self.spawn_rate = 0
        self.stats = types.SimpleNamespace(entries={}, total=types.SimpleNamespace(num_requests=0, fail_ratio=0.0, avg_response_time=0, get_response_time_percentile=lambda x: 0))  # type: ignore[attr-defined]
        self.greenlet = types.SimpleNamespace(join=lambda: None)

    def start(self, user_count: int, spawn_rate: int):
        self.started = True
        self.user_count = user_count
        self.spawn_rate = spawn_rate

    def quit(self):
        self.stopped = True


@pytest.fixture
def dummy_scheduler():
    return DummyScheduler()
