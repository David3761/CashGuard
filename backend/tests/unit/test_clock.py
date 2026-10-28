from datetime import UTC, date, datetime, time, timedelta

import pytest

from app import clock
from app.clock import BUCHAREST, FixedClock, RealClock, local_date, to_local


def utc(y, mo, d, h, mi):
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def test_fixed_clock_returns_its_date():
    c = FixedClock.on(date(2026, 6, 15))
    assert c.today() == date(2026, 6, 15)
    assert c.now() == datetime(2026, 6, 15, 12, 0, tzinfo=BUCHAREST)


def test_fixed_clock_rejects_naive_datetime():
    with pytest.raises(ValueError, match="naive"):
        FixedClock(datetime(2026, 6, 15, 12, 0))


def test_real_clock_now_is_tz_aware_bucharest():
    now = RealClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() in (timedelta(hours=2), timedelta(hours=3))


def test_local_date_late_utc_evening_is_next_bucharest_day_in_summer():
    # 21:30Z in June = 00:30 EEST (UTC+3) the next day
    assert local_date(utc(2026, 6, 14, 21, 30)) == date(2026, 6, 15)
    assert FixedClock(utc(2026, 6, 14, 21, 30)).today() == date(2026, 6, 15)


def test_local_date_just_before_bucharest_midnight_is_same_day():
    assert local_date(utc(2026, 6, 14, 20, 59)) == date(2026, 6, 14)


def test_dst_end_day_offsets_before_and_after_0400_local():
    # 2026-10-25: clocks go back from 04:00 EEST to 03:00 EET (01:00Z)
    before = to_local(utc(2026, 10, 25, 0, 59))
    after = to_local(utc(2026, 10, 25, 1, 0))
    assert before.time() == time(3, 59) and before.utcoffset() == timedelta(hours=3)
    assert after.time() == time(3, 0) and after.utcoffset() == timedelta(hours=2)
    assert before.date() == after.date() == date(2026, 10, 25)


def test_dst_end_day_midnight_boundaries():
    assert local_date(utc(2026, 10, 24, 21, 30)) == date(2026, 10, 25)  # 00:30 EEST
    assert local_date(utc(2026, 10, 25, 21, 30)) == date(2026, 10, 25)  # 23:30 EET
    assert local_date(utc(2026, 10, 25, 22, 30)) == date(2026, 10, 26)  # 00:30 EET


def test_set_clock_swaps_the_module_clock():
    original = clock.get_clock()
    try:
        clock.set_clock(FixedClock.on(date(2026, 6, 15)))
        assert clock.today() == date(2026, 6, 15)
        assert clock.now().date() == date(2026, 6, 15)
    finally:
        clock.set_clock(original)
