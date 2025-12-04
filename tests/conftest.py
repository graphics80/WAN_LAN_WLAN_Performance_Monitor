import os
import sys
from pathlib import Path
from typing import List

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def restore_env():
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


@pytest.fixture
def dummy_scheduler():
    return DummyScheduler()
