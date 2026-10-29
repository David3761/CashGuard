"""Calendar utilities for the engine (pure, plain `date`s, no clock).

Bounds, used the same way everywhere in the engine:
- `occurrences`, `paydays_between`: `(start, end]`, i.e. "from tomorrow to the deadline".
  Income or a bill dated `start` (today) is treated as already processed.
- `iter_days`, `months_between`: `[start, end]`, i.e. the plan horizon including today.
An `end` before `start` always gives an empty list, never an error.
"""

import calendar
from collections.abc import Iterable
from datetime import date, timedelta


def days_in_month(year: int, month: int) -> int:
    """Number of days in `month` (1–12) of `year`; raises `ValueError` for any other month."""
    return calendar.monthrange(year, month)[1]


def _clamped(year: int, month: int, day_of_month: int) -> date:
    return date(year, month, min(day_of_month, days_in_month(year, month)))


def occurrences(day_of_month: int, start: date, end: date) -> list[date]:
    """Dates in `(start, end]` falling on `day_of_month`, one per month.

    A day past the month's end lands on its last day (31 → 28 Feb 2027, 29 Feb 2028).
    """
    if not 1 <= day_of_month <= 31:
        raise ValueError(f"day_of_month must be 1–31, got {day_of_month}")
    return [
        d
        for year, month in months_between(start, end)
        if start < (d := _clamped(year, month, day_of_month)) <= end
    ]


def paydays_between(days_of_month: Iterable[int], start: date, end: date) -> list[date]:
    """Sorted, unique dates in `(start, end]` on which any of `days_of_month` falls."""
    return sorted({d for day in days_of_month for d in occurrences(day, start, end)})


def months_between(start: date, end: date) -> list[tuple[int, int]]:
    """Every `(year, month)` touched by `[start, end]`, in order."""
    first, last = start.year * 12 + start.month - 1, end.year * 12 + end.month - 1
    return [(m // 12, m % 12 + 1) for m in range(first, last + 1)]


def iter_days(start: date, end: date) -> list[date]:
    """Every day in `[start, end]`, in order."""
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def next_monday(d: date) -> date:
    """The first Monday on or after `d` (a Monday returns itself)."""
    return d + timedelta(days=(7 - d.weekday()) % 7)
