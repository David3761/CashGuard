from datetime import date, timedelta
from itertools import pairwise

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.engine.calendar import (
    days_in_month,
    iter_days,
    months_between,
    next_monday,
    occurrences,
    paydays_between,
)

dates = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))
day_numbers = st.integers(min_value=1, max_value=31)


# ── days_in_month ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("year", "month", "expected"),
    [(2026, 1, 31), (2026, 4, 30), (2027, 2, 28), (2028, 2, 29), (2100, 2, 28), (2000, 2, 29)],
)
def test_days_in_month_handles_short_and_leap_months(year: int, month: int, expected: int) -> None:
    assert days_in_month(year, month) == expected


@pytest.mark.parametrize("month", [0, 13])
def test_days_in_month_rejects_invalid_month(month: int) -> None:
    with pytest.raises(ValueError):
        days_in_month(2026, month)


# ── occurrences: (start, end] ────────────────────────────────────────────────


def test_occurrences_matei_salary_from_sim_date_to_deadline() -> None:
    result = occurrences(10, date(2026, 6, 15), date(2026, 12, 31))
    assert result == [date(2026, m, 10) for m in range(7, 13)]


@pytest.mark.parametrize(
    ("day", "start", "end", "expected"),
    [
        (31, date(2027, 2, 1), date(2027, 2, 28), date(2027, 2, 28)),
        (30, date(2027, 2, 1), date(2027, 2, 28), date(2027, 2, 28)),
        (29, date(2027, 2, 1), date(2027, 2, 28), date(2027, 2, 28)),
        (29, date(2028, 2, 1), date(2028, 2, 29), date(2028, 2, 29)),
        (31, date(2026, 4, 1), date(2026, 4, 30), date(2026, 4, 30)),
    ],
)
def test_occurrences_clamps_day_to_end_of_short_month(
    day: int, start: date, end: date, expected: date
) -> None:
    assert occurrences(day, start, end) == [expected]


def test_occurrences_excludes_start_day() -> None:
    # income dated today is already in the balance once processed (E2 decision)
    assert occurrences(10, date(2026, 7, 10), date(2026, 8, 9)) == []


def test_occurrences_includes_end_day() -> None:
    assert occurrences(10, date(2026, 7, 10), date(2026, 8, 10)) == [date(2026, 8, 10)]


def test_occurrences_start_equals_end_is_empty() -> None:
    assert occurrences(15, date(2026, 6, 15), date(2026, 6, 15)) == []


def test_occurrences_end_before_start_is_empty() -> None:
    assert occurrences(10, date(2026, 12, 31), date(2026, 6, 15)) == []


@pytest.mark.parametrize("day", [0, 32, -1])
def test_occurrences_rejects_invalid_day_of_month(day: int) -> None:
    with pytest.raises(ValueError):
        occurrences(day, date(2026, 6, 15), date(2026, 12, 31))


def test_occurrences_crosses_year_boundary() -> None:
    result = occurrences(5, date(2026, 12, 1), date(2027, 2, 5))
    assert result == [date(2026, 12, 5), date(2027, 1, 5), date(2027, 2, 5)]


@given(day=day_numbers, start=dates, span=st.integers(min_value=0, max_value=800))
def test_occurrences_are_in_range_sorted_unique_one_per_month(day: int, start: date, span: int) -> None:
    end = start + timedelta(days=span)
    result = occurrences(day, start, end)
    assert all(start < d <= end for d in result)
    assert result == sorted(set(result))
    assert len({(d.year, d.month) for d in result}) == len(result)


# ── paydays_between: (start, end], several income days merged ───────────────


def test_paydays_between_merges_several_income_days_sorted() -> None:
    result = paydays_between([10, 1], date(2026, 6, 15), date(2026, 8, 15))
    assert result == [date(2026, 7, 1), date(2026, 7, 10), date(2026, 8, 1), date(2026, 8, 10)]


def test_paydays_between_deduplicates_days_clamped_to_same_date() -> None:
    # 30 and 31 both fall on 28 Feb 2027
    assert paydays_between([30, 31], date(2027, 2, 1), date(2027, 2, 28)) == [date(2027, 2, 28)]


def test_paydays_between_pot_example_from_e10() -> None:
    # pot by 15 Aug from 15 Jun, salary on the 10th → 2 paydays (10 Jul, 10 Aug)
    assert paydays_between([10], date(2026, 6, 15), date(2026, 8, 15)) == [
        date(2026, 7, 10),
        date(2026, 8, 10),
    ]


def test_paydays_between_no_income_days_is_empty() -> None:
    assert paydays_between([], date(2026, 6, 15), date(2026, 12, 31)) == []


# ── months_between: [start, end] ─────────────────────────────────────────────


def test_months_between_matei_horizon_has_seven_months() -> None:
    assert months_between(date(2026, 6, 15), date(2026, 12, 31)) == [(2026, m) for m in range(6, 13)]


def test_months_between_same_day_is_one_month() -> None:
    assert months_between(date(2026, 6, 15), date(2026, 6, 15)) == [(2026, 6)]


def test_months_between_crosses_year_boundary() -> None:
    assert months_between(date(2026, 11, 30), date(2027, 2, 1)) == [
        (2026, 11),
        (2026, 12),
        (2027, 1),
        (2027, 2),
    ]


def test_months_between_end_before_start_is_empty() -> None:
    assert months_between(date(2026, 7, 1), date(2026, 6, 30)) == []


# ── iter_days: [start, end] ──────────────────────────────────────────────────


def test_iter_days_includes_both_ends() -> None:
    assert iter_days(date(2026, 6, 15), date(2026, 6, 17)) == [
        date(2026, 6, 15),
        date(2026, 6, 16),
        date(2026, 6, 17),
    ]


def test_iter_days_start_equals_end_is_one_day() -> None:
    assert iter_days(date(2026, 6, 15), date(2026, 6, 15)) == [date(2026, 6, 15)]


def test_iter_days_end_before_start_is_empty() -> None:
    assert iter_days(date(2026, 6, 16), date(2026, 6, 15)) == []


def test_iter_days_across_dst_change_has_no_gap_or_duplicate() -> None:
    # Europe/Bucharest switches to winter time on 2026-10-25
    result = iter_days(date(2026, 10, 24), date(2026, 10, 26))
    assert result == [date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26)]


def test_iter_days_across_leap_day() -> None:
    assert iter_days(date(2028, 2, 28), date(2028, 3, 1)) == [
        date(2028, 2, 28),
        date(2028, 2, 29),
        date(2028, 3, 1),
    ]


@given(start=dates, span=st.integers(min_value=-5, max_value=800))
def test_iter_days_length_matches_span_and_is_consecutive(start: date, span: int) -> None:
    end = start + timedelta(days=span)
    result = iter_days(start, end)
    assert len(result) == max(0, span + 1)
    assert all(b - a == timedelta(days=1) for a, b in pairwise(result))


# ── next_monday: on or after ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("d", "expected"),
    [
        (date(2026, 6, 15), date(2026, 6, 15)),  # Monday → same day (sim start)
        (date(2026, 6, 14), date(2026, 6, 15)),  # Sunday → +1
        (date(2026, 6, 16), date(2026, 6, 22)),  # Tuesday → +6
        (date(2026, 12, 30), date(2027, 1, 4)),  # across the year
    ],
)
def test_next_monday_is_on_or_after(d: date, expected: date) -> None:
    assert next_monday(d) == expected


@given(d=dates)
def test_next_monday_is_a_monday_within_six_days(d: date) -> None:
    result = next_monday(d)
    assert result.isoweekday() == 1
    assert timedelta(0) <= result - d <= timedelta(days=6)
