"""The only source of "now". Never call `datetime.now()` elsewhere (arch 4.3).

Day boundaries are Europe/Bucharest. The simulator (B10) plugs a `SimClock` in with `set_clock`.
"""

from datetime import date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

BUCHAREST = ZoneInfo("Europe/Bucharest")


def to_local(instant: datetime) -> datetime:
    """The same instant in Bucharest time. Naive datetimes are rejected."""
    if instant.tzinfo is None:
        raise ValueError("naive datetime: an instant needs a time zone")
    return instant.astimezone(BUCHAREST)


def local_date(instant: datetime) -> date:
    """The Bucharest calendar day an instant falls on."""
    return to_local(instant).date()


class Clock(Protocol):
    def today(self) -> date: ...

    def now(self) -> datetime: ...


class RealClock:
    def now(self) -> datetime:
        return datetime.now(BUCHAREST)

    def today(self) -> date:
        return self.now().date()


class FixedClock:
    """A clock frozen at one instant (tests)."""

    def __init__(self, at: datetime) -> None:
        self._at = to_local(at)

    @classmethod
    def on(cls, day: date, at: time = time(12, 0)) -> "FixedClock":
        return cls(datetime.combine(day, at, tzinfo=BUCHAREST))

    def now(self) -> datetime:
        return self._at

    def today(self) -> date:
        return self._at.date()


_clock: Clock = RealClock()


def get_clock() -> Clock:
    return _clock


def set_clock(clock: Clock) -> None:
    global _clock
    _clock = clock


def today() -> date:
    return _clock.today()


def now() -> datetime:
    return _clock.now()
