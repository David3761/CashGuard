from datetime import date
from pathlib import Path

import pytest

from app import clock
from app.clock import FixedClock

pytest_plugins = ["tests.fixtures.db"]

SIM_START = date(2026, 6, 15)

_MARKER_BY_FOLDER = {"db": pytest.mark.db, "api": pytest.mark.api, "ws": pytest.mark.ws}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    # tests/db/* → marker db, tests/api/* → api, tests/ws/* → ws
    for item in items:
        folder = Path(str(item.fspath)).parent.name
        if folder in _MARKER_BY_FOLDER:
            item.add_marker(_MARKER_BY_FOLDER[folder])


@pytest.fixture(autouse=True)
def fixed_clock():
    """Every test runs at 2026-06-15 12:00 Bucharest unless it sets another clock."""
    original = clock.get_clock()
    fixed = FixedClock.on(SIM_START)
    clock.set_clock(fixed)
    yield fixed
    clock.set_clock(original)
