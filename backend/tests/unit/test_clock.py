"""F1.3: the app clock. Day boundaries are Europe/Bucharest, whatever the server's time zone.

Instants are written in UTC (`…Z`) so that every case is unambiguous, including the DST nights.
"""

import os
import subprocess
import sys
import threading
import time
from datetime import UTC, date, datetime, timedelta, tzinfo
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app import clock
from app.clock import APP_TZ, Clock, FixedClock, RealClock
from app.config import BACKEND_DIR


class _Clock:
    """A hand-made clock for the validation tests: it returns exactly what it's given."""

    def __init__(self, now: object, today: object) -> None:
        self._now, self._today = now, today

    def now(self) -> datetime:
        return self._now  # type: ignore[return-value]

    def today(self) -> date:
        return self._today  # type: ignore[return-value]


class _UncachedZoneClock:
    """A correct clock whose zone is an equal but separate ZoneInfo object (no_cache)."""

    zone = ZoneInfo.no_cache("Europe/Bucharest")

    def now(self) -> datetime:
        return datetime.now(self.zone)  # noqa: TID251 - a stand-in for a real clock (e.g. SimClock)

    def today(self) -> date:
        return self.now().date()


def _at(instant: str) -> FixedClock:
    return FixedClock(datetime.fromisoformat(instant))


# ── FixedClock and RealClock ─────────────────────────────────────────────────────────────────


def test_app_time_zone_is_bucharest() -> None:
    assert APP_TZ.key == "Europe/Bucharest"


def test_fixed_clock_gives_its_instant_in_bucharest() -> None:
    fixed = _at("2026-06-15T09:00:00Z")

    assert fixed.today() == date(2026, 6, 15)
    assert fixed.now() == datetime(2026, 6, 15, 9, tzinfo=UTC)  # the same instant
    assert fixed.now().tzinfo is APP_TZ
    assert fixed.now().isoformat() == "2026-06-15T12:00:00+03:00"


def test_fixed_clock_shows_its_instant_in_failure_messages() -> None:
    assert repr(_at("2026-06-15T09:00:00Z")) == "FixedClock(2026-06-15T12:00:00+03:00)"


def test_fixed_clock_stands_still() -> None:
    fixed = _at("2026-06-15T09:00:00Z")

    assert fixed.now() == fixed.now()


def test_fixed_clock_accepts_any_aware_datetime() -> None:
    india = datetime.fromisoformat("2026-06-15T05:30:00+05:30")

    assert FixedClock(india).now().isoformat() == "2026-06-15T03:00:00+03:00"


class _NoOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> timedelta | None:
        return None

    def tzname(self, dt: datetime | None) -> str | None:
        return None

    def dst(self, dt: datetime | None) -> timedelta | None:
        return None


@pytest.mark.parametrize(
    "naive",
    [
        datetime(2026, 6, 15, 9),  # noqa: DTZ001 - the naive input under test
        datetime(2026, 6, 15, 9, tzinfo=_NoOffset()),  # tzinfo set, but no offset: still naive
    ],
)
def test_fixed_clock_rejects_a_naive_datetime(naive: datetime) -> None:
    # A naive time silently means "the server's local time".
    with pytest.raises(ValueError, match="timezone-aware"):
        FixedClock(naive)


@pytest.mark.parametrize("not_a_datetime", [date(2026, 6, 15), "2026-06-15T09:00:00Z", 1781481600])
def test_fixed_clock_rejects_what_is_not_a_datetime(not_a_datetime: object) -> None:
    with pytest.raises(TypeError, match="timezone-aware datetime"):
        FixedClock(not_a_datetime)  # type: ignore[arg-type]


def test_real_clock_is_now_in_bucharest() -> None:
    reference = datetime.now(UTC)  # noqa: TID251 - an independent reference for RealClock

    now = RealClock().now()

    assert now.tzinfo is APP_TZ
    assert now.utcoffset() in {timedelta(hours=2), timedelta(hours=3)}
    assert abs(now - reference) < timedelta(seconds=5)


def test_the_os_time_zone_changes_nothing() -> None:
    # TZ is an OS/container variable only (arch Q25): the app never uses server-local time.
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("TZ", "America/New_York")
            time.tzset()

            now = RealClock().now()
            reference = datetime.now(UTC)  # noqa: TID251 - an independent reference

            assert now.utcoffset() in {timedelta(hours=2), timedelta(hours=3)}
            # the instant too: a clock labelling New York's wall time as Bucharest would pass the
            # offset check but be 6-7 hours off
            assert abs(now - reference) < timedelta(seconds=5)
            assert _at("2026-06-14T21:30:00Z").today() == date(2026, 6, 15)
    finally:
        time.tzset()  # back to the restored TZ, even if an assertion failed


# ── day boundaries ───────────────────────────────────────────────────────────────────────────

BOUNDARIES = [
    # summer: UTC+3, so midnight is 21:00Z (work-breakdown F1: 21:30Z is already the 15th)
    ("2026-06-14T20:59:59Z", "2026-06-14T23:59:59+03:00"),
    ("2026-06-14T21:00:00Z", "2026-06-15T00:00:00+03:00"),
    ("2026-06-14T21:30:00Z", "2026-06-15T00:30:00+03:00"),
    # DST ends 2026-10-25 at 01:00Z: 04:00 EEST (+03) becomes 03:00 EET (+02)
    ("2026-10-24T20:59:59Z", "2026-10-24T23:59:59+03:00"),
    ("2026-10-24T21:00:00Z", "2026-10-25T00:00:00+03:00"),
    ("2026-10-25T00:59:59Z", "2026-10-25T03:59:59+03:00"),
    ("2026-10-25T01:00:00Z", "2026-10-25T03:00:00+02:00"),
    # ...so that day's midnight moves from 21:00Z to 22:00Z
    ("2026-10-25T21:59:59Z", "2026-10-25T23:59:59+02:00"),
    ("2026-10-25T22:00:00Z", "2026-10-26T00:00:00+02:00"),
    # DST starts 2026-03-29 at 01:00Z: 03:00 EET (+02) becomes 04:00 EEST (+03)
    ("2026-03-28T21:59:59Z", "2026-03-28T23:59:59+02:00"),
    ("2026-03-28T22:00:00Z", "2026-03-29T00:00:00+02:00"),
    ("2026-03-29T00:59:59Z", "2026-03-29T02:59:59+02:00"),
    ("2026-03-29T01:00:00Z", "2026-03-29T04:00:00+03:00"),
    ("2026-03-29T20:59:59Z", "2026-03-29T23:59:59+03:00"),
    ("2026-03-29T21:00:00Z", "2026-03-30T00:00:00+03:00"),
    # the year boundary
    ("2026-12-31T21:59:59Z", "2026-12-31T23:59:59+02:00"),
    ("2026-12-31T22:00:00Z", "2027-01-01T00:00:00+02:00"),
    # a leap day
    ("2028-02-28T21:59:59Z", "2028-02-28T23:59:59+02:00"),
    ("2028-02-28T22:00:00Z", "2028-02-29T00:00:00+02:00"),
    ("2028-02-29T21:59:59Z", "2028-02-29T23:59:59+02:00"),
    ("2028-02-29T22:00:00Z", "2028-03-01T00:00:00+02:00"),
]


@pytest.mark.parametrize(("instant", "local"), BOUNDARIES)
def test_day_boundaries_follow_bucharest_time(instant: str, local: str) -> None:
    fixed = _at(instant)

    assert fixed.now().isoformat() == local
    assert fixed.today() == date.fromisoformat(local[:10])


def test_the_repeated_hour_keeps_two_distinct_instants() -> None:
    # 03:30 happens twice on 2026-10-25; `fold` picks the first (+03) or the second (+02).
    # Instants are compared in UTC: Python never treats a datetime in a repeated (or skipped)
    # hour as == to one in another zone, even at the same instant (PEP 495).
    first = FixedClock(datetime(2026, 10, 25, 3, 30, tzinfo=APP_TZ, fold=0))
    second = FixedClock(datetime(2026, 10, 25, 3, 30, tzinfo=APP_TZ, fold=1))

    assert first.now().astimezone(UTC) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)
    assert second.now().astimezone(UTC) == datetime(2026, 10, 25, 1, 30, tzinfo=UTC)
    assert first.now().isoformat() == "2026-10-25T03:30:00+03:00"
    assert second.now().isoformat() == "2026-10-25T03:30:00+02:00"
    assert first.today() == second.today() == date(2026, 10, 25)


def test_a_skipped_local_time_becomes_the_real_wall_time() -> None:
    # 03:30 never happens on 2026-03-29 (03:00 jumps to 04:00). The clock must not hand out a
    # wall time that never existed: quiet hours (C7) read now().hour.
    skipped = FixedClock(datetime(2026, 3, 29, 3, 30, tzinfo=APP_TZ))

    assert skipped.now().isoformat() == "2026-03-29T04:30:00+03:00"
    assert skipped.now().hour == 4


@given(
    moment=st.datetimes(
        min_value=datetime(2000, 1, 1),  # noqa: DTZ001 - hypothesis bounds are naive
        max_value=datetime(2100, 1, 1),  # noqa: DTZ001
        timezones=st.timezones(),
    )
)
def test_today_is_the_utc_date_or_the_day_after(moment: datetime) -> None:
    # Bucharest is always UTC+2 or UTC+3, so its date is never behind UTC's.
    fixed = FixedClock(moment)
    utc_date = moment.astimezone(UTC).date()

    assert fixed.now().astimezone(UTC) == moment.astimezone(UTC)  # same instant (PEP 495)
    assert fixed.now().utcoffset() in {timedelta(hours=2), timedelta(hours=3)}
    assert fixed.today() in {utc_date, utc_date + timedelta(days=1)}


# ── the installed clock ──────────────────────────────────────────────────────────────────────


def test_the_default_clock_is_the_real_one() -> None:
    # In a fresh interpreter: inside the test session the conftest installs a RealClock itself.
    code = "from app import clock; print(type(clock.get_clock()).__name__)"
    result = subprocess.run(  # noqa: S603 - our own interpreter and a fixed snippet
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env={"PATH": os.environ.get("PATH", "")},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "RealClock"


def test_set_clock_installs_a_clock_and_returns_the_previous_one() -> None:
    fixed = _at("2026-06-15T09:00:00Z")

    previous = clock.set_clock(fixed)

    assert isinstance(previous, RealClock)
    assert clock.get_clock() is fixed
    assert clock.now() == fixed.now()
    assert clock.today() == date(2026, 6, 15)
    assert clock.set_clock(previous) is fixed
    assert clock.get_clock() is previous


_JUNE_15 = datetime(2026, 6, 15, 12, tzinfo=APP_TZ)


@pytest.mark.parametrize(
    ("bad", "error"),
    [
        (object(), TypeError),
        (datetime, TypeError),  # the class: its now() is naive server-local time
        (datetime(2026, 6, 15, 9, tzinfo=UTC), TypeError),  # an instance has now() too
        (RealClock, TypeError),  # the class instead of an instance
        (_Clock(datetime(2026, 6, 15, 12), date(2026, 6, 15)), TypeError),  # noqa: DTZ001 - naive now()
        (_Clock("2026-06-15T12:00", date(2026, 6, 15)), TypeError),  # now() not a datetime
        (_Clock(_JUNE_15, _JUNE_15), TypeError),  # today() a datetime, not a date
        (_Clock(_JUNE_15, "2026-06-15"), TypeError),  # today() not a date
        (
            _Clock(datetime(2026, 6, 15, 9, tzinfo=UTC), date(2026, 6, 15)),
            ValueError,
        ),  # not Bucharest
        (_Clock(_JUNE_15, date(2026, 6, 16)), ValueError),  # today() isn't now()'s date
    ],
)
def test_set_clock_rejects_what_is_not_a_working_clock(bad: object, error: type[Exception]) -> None:
    with pytest.raises(error, match="clock"):
        clock.set_clock(bad)  # type: ignore[arg-type]
    with pytest.raises(error, match="clock"), clock.use_clock(bad):  # type: ignore[arg-type]
        pass  # pragma: no cover - never reached

    assert isinstance(clock.get_clock(), RealClock)


def test_set_clock_accepts_an_equal_but_separate_zone_object() -> None:
    working = _UncachedZoneClock()

    assert clock.set_clock(working) is not working
    assert clock.get_clock() is working


# ── use_clock ────────────────────────────────────────────────────────────────────────────────


def test_use_clock_installs_a_clock_for_the_block_only() -> None:
    fixed = _at("2026-06-15T09:00:00Z")

    with clock.use_clock(fixed) as installed:
        assert installed is fixed
        assert clock.today() == date(2026, 6, 15)

    assert isinstance(clock.get_clock(), RealClock)


def test_use_clock_restores_even_when_the_block_fails() -> None:
    with pytest.raises(RuntimeError, match="boom"), clock.use_clock(_at("2026-06-15T09:00:00Z")):
        raise RuntimeError("boom")

    assert isinstance(clock.get_clock(), RealClock)


def test_nested_use_clock_blocks_unwind_in_order() -> None:
    outer, inner = _at("2026-06-15T09:00:00Z"), _at("2026-07-01T09:00:00Z")

    with clock.use_clock(outer):
        with clock.use_clock(inner):
            assert clock.get_clock() is inner
        assert clock.get_clock() is outer
    assert isinstance(clock.get_clock(), RealClock)


def test_overlapping_use_clock_blocks_each_remove_only_their_own() -> None:
    # Thread A enters, then B enters, then A leaves first (not in LIFO order). B must keep its
    # clock, and once both are gone the original clock is back.
    first, second = _at("2026-06-15T09:00:00Z"), _at("2026-07-01T09:00:00Z")
    a_entered, b_entered, a_left = threading.Event(), threading.Event(), threading.Event()
    seen: dict[str, object] = {}

    def a() -> None:
        with clock.use_clock(first):
            a_entered.set()
            b_entered.wait(5)
        a_left.set()

    def b() -> None:
        a_entered.wait(5)
        with clock.use_clock(second):
            b_entered.set()
            a_left.wait(5)
            seen["b, after a left"] = clock.get_clock()

    threads = [threading.Thread(target=a), threading.Thread(target=b)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert seen["b, after a left"] is second
    assert isinstance(clock.get_clock(), RealClock)


def test_many_threads_using_clocks_at_once_leave_the_original_installed() -> None:
    clocks = [_at(f"2026-06-{day:02d}T09:00:00Z") for day in range(1, 21)]
    start = threading.Barrier(len(clocks))
    errors: list[BaseException] = []

    def work(own: FixedClock) -> None:
        try:
            start.wait(5)
            for _ in range(50):
                with clock.use_clock(own):
                    assert isinstance(clock.get_clock(), FixedClock)
        except BaseException as error:  # reported below
            errors.append(error)

    threads = [threading.Thread(target=work, args=(own,)) for own in clocks]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)

    assert errors == []
    assert isinstance(clock.get_clock(), RealClock)


# ── the contract every clock keeps ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("candidate", "real_time"),
    [
        (RealClock(), True),
        (_UncachedZoneClock(), True),
        (_at("2026-10-25T01:00:00Z"), False),
    ],
)
def test_every_clock_keeps_the_contract(candidate: Clock, real_time: bool) -> None:
    # The rules bomboe's SimClock (B10) must also pass: add it to the list above.
    before = candidate.now()
    today = candidate.today()
    after = candidate.now()

    assert isinstance(candidate, Clock)
    assert getattr(before.tzinfo, "key", None) == "Europe/Bucharest"
    assert before.utcoffset() == before.astimezone(APP_TZ).utcoffset()
    assert type(today) is date  # a date, not a datetime
    assert today in {before.date(), after.date()}  # both sides: a real clock may cross midnight
    if real_time:
        reference = datetime.now(UTC)  # noqa: TID251 - an independent reference
        assert abs(before - reference) < timedelta(seconds=5)


# ── bomboe's helpers kept by the integration (FixedClock.on, to_local, local_date) ───────────


def _utc(y: int, mo: int, d: int, h: int, mi: int) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def test_fixed_clock_on_is_noon_bucharest_by_default() -> None:
    c = FixedClock.on(date(2026, 6, 15))
    assert c.today() == date(2026, 6, 15)
    assert c.now() == datetime(2026, 6, 15, 12, 0, tzinfo=clock.APP_TZ)


def test_local_date_late_utc_evening_is_next_bucharest_day_in_summer() -> None:
    assert clock.local_date(_utc(2026, 6, 14, 21, 30)) == date(2026, 6, 15)
    assert clock.local_date(_utc(2026, 6, 14, 20, 59)) == date(2026, 6, 14)


def test_to_local_on_the_dst_end_day() -> None:
    before = clock.to_local(_utc(2026, 10, 25, 0, 59))
    after = clock.to_local(_utc(2026, 10, 25, 1, 0))
    assert before.utcoffset() == timedelta(hours=3)
    assert after.utcoffset() == timedelta(hours=2)
    assert clock.local_date(_utc(2026, 10, 25, 22, 30)) == date(2026, 10, 26)


def test_to_local_rejects_a_naive_datetime() -> None:
    with pytest.raises(ValueError, match="naive"):
        clock.to_local(datetime(2026, 6, 15, 12, 0))  # noqa: DTZ001
