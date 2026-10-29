"""The app clock (F1.3). The only module allowed to read the wall clock (ruff TID251).

Day boundaries are always Europe/Bucharest (arch Q25), whatever the server's `TZ`. The shell gets
the time from `clock.now()` / `clock.today()`; pure cores receive `today` as a parameter
(work-breakdown 0.3 rule 3). One clock is installed per process (1 worker, H-2): `RealClock` by
default, bomboe's `SimClock` (B10) in SIM_MODE via `set_clock()`, and a `FixedClock` in tests,
preferably for a block only: `with use_clock(FixedClock(...)):`.
"""

import itertools
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Final, Protocol, runtime_checkable
from zoneinfo import ZoneInfo

APP_TZ: Final = ZoneInfo("Europe/Bucharest")  # resolved at import: a missing tz database fails fast


@runtime_checkable
class Clock(Protocol):
    """What every clock provides. Contract (tests/unit/test_clock.py checks it for each clock):
    `now()` is timezone-aware in APP_TZ, and `today()` is `now().date()`, the Bucharest date.
    JSON timestamps are UTC (arch 9.1): converting is the API layer's job. To compare instants
    from different zones, compare `.astimezone(UTC)` values: during the repeated DST hour, Python
    never treats a Bucharest datetime as == to the same instant in UTC (PEP 495)."""

    def now(self) -> datetime: ...

    def today(self) -> date: ...


class RealClock:
    """The wall clock, in Bucharest time."""

    def now(self) -> datetime:
        return datetime.now(APP_TZ)

    def today(self) -> date:
        return self.now().date()


class FixedClock:
    """A clock stopped at one instant (tests). Write instants in UTC to keep them unambiguous."""

    def __init__(self, at: datetime) -> None:
        if not isinstance(at, datetime):
            raise TypeError(f"FixedClock needs a timezone-aware datetime, got {at!r}")
        if at.utcoffset() is None:
            raise ValueError(f"FixedClock needs a timezone-aware datetime, got {at!r}")
        # Through UTC: astimezone() is a no-op on a datetime already in APP_TZ, which would keep a
        # local time that never existed (03:30 on the spring-forward night).
        self._at = at.astimezone(UTC).astimezone(APP_TZ)

    def now(self) -> datetime:
        return self._at

    def today(self) -> date:
        return self._at.date()

    def __repr__(self) -> str:
        return f"FixedClock({self._at.isoformat()})"


_lock = threading.Lock()
_installed: Clock = RealClock()  # set_clock(): the process-wide clock
_blocks: dict[int, Clock] = {}  # open use_clock() blocks, in the order they were entered
_block_ids = itertools.count()


def _checked(clock: object) -> Clock:
    """`clock` if it really works as a Clock (both methods are called once); else an error."""
    if isinstance(clock, type) or not isinstance(clock, Clock):
        raise TypeError(f"a clock instance with now() and today() is required, got {clock!r}")
    before = clock.now()
    if not isinstance(before, datetime) or before.utcoffset() is None:
        raise TypeError(f"the clock's now() must return an aware datetime, got {before!r}")
    if before.utcoffset() != before.astimezone(APP_TZ).utcoffset():
        raise ValueError(f"the clock's now() must be Bucharest time, got {before.isoformat()}")
    today = clock.today()
    if not isinstance(today, date) or isinstance(today, datetime):
        raise TypeError(f"the clock's today() must return a date, got {today!r}")
    if today not in {before.date(), clock.now().date()}:  # both: a real clock may cross midnight
        raise ValueError(f"the clock's today() ({today}) must be now()'s date ({before.date()})")
    return clock


def get_clock() -> Clock:
    """The installed clock: the innermost open `use_clock()` block's, else `set_clock()`'s."""
    with _lock:
        return next(reversed(_blocks.values())) if _blocks else _installed


def set_clock(clock: Clock) -> Clock:
    """Install `clock` for the whole process (B10's SimClock) and return the previous one."""
    global _installed
    checked = _checked(clock)
    with _lock:
        previous, _installed = _installed, checked
    return previous


@contextmanager
def use_clock(clock: Clock) -> Iterator[Clock]:
    """Install `clock` for the `with` block, and remove it on exit, also after an error.

    Blocks may overlap (threads) and end in any order: each removes only its own clock, so the
    others keep theirs ("restore the previous clock" would put back a wrong one)."""
    checked = _checked(clock)
    with _lock:
        block = next(_block_ids)
        _blocks[block] = checked
    try:
        yield checked
    finally:
        with _lock:
            del _blocks[block]


def now() -> datetime:
    """The current time, from the installed clock."""
    return get_clock().now()


def today() -> date:
    """Today's date in Bucharest, from the installed clock."""
    return get_clock().today()
