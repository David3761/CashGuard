from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

pytest.importorskip("app.domain", reason="needs F2 app.domain (David G.)")

from app.engine.baselines import Member, is_active, person_weight, scale_from_members

D = Decimal
TODAY = date(2026, 6, 15)
JULY = (date(2026, 7, 1), date(2026, 7, 31))

PARTNER: Member = ("adult", None, None, None)
IOANA_HOUSEHOLD: list[Member] = [PARTNER, ("child", 7, None, None), ("child", 11, None, None)]
MOTHER_IN_JULY: Member = ("adult", 64, *JULY)

members = st.lists(
    st.one_of(
        st.tuples(st.just("adult"), st.none() | st.integers(14, 100), st.none(), st.none()),
        st.tuples(st.just("child"), st.integers(0, 17), st.none(), st.none()),
    ),
    max_size=10,
)


# ── scale_from_members: the user is the first adult (1.0), facts list the others ──


@pytest.mark.parametrize(
    ("household", "expected"),
    [
        ([], D("1.0")),  # Matei, alone
        ([PARTNER], D("1.5")),  # Andrei and his partner
        (IOANA_HOUSEHOLD, D("2.1")),  # Ioana: partner + children 7 and 11
        ([PARTNER, PARTNER], D("2.0")),  # flatmates count as adults
    ],
)
def test_household_scale_matches_arch_examples(household: list[Member], expected: Decimal) -> None:
    assert scale_from_members(household, TODAY) == expected


def test_household_scale_returns_exact_decimal() -> None:
    scale = scale_from_members(IOANA_HOUSEHOLD, TODAY)
    assert isinstance(scale, Decimal)
    assert str(scale) == "2.1"


@pytest.mark.parametrize(
    ("on_date", "expected"),
    [
        (date(2026, 6, 30), D("2.1")),  # before the visit
        (date(2026, 7, 1), D("2.6")),  # first day, inclusive
        (date(2026, 7, 10), D("2.6")),
        (date(2026, 7, 31), D("2.6")),  # last day, inclusive
        (date(2026, 8, 1), D("2.1")),  # after the visit
    ],
)
def test_household_scale_counts_temporary_member_only_inside_window(on_date: date, expected: Decimal) -> None:
    # arch 16.3 #13: "mama stă la noi în iulie" → 2.1 → 2.6, only in July
    assert scale_from_members([*IOANA_HOUSEHOLD, MOTHER_IN_JULY], on_date) == expected


def test_household_scale_permanent_member_counts_from_valid_from() -> None:
    baby: Member = ("child", 0, date(2026, 9, 1), None)
    assert scale_from_members([baby], date(2026, 8, 31)) == D("1.0")
    assert scale_from_members([baby], date(2027, 9, 1)) == D("1.3")


def test_household_scale_same_member_different_persona() -> None:
    # personalisation: a child changes Ioana's household, Matei's stays 1.0
    child: Member = ("child", 7, None, None)
    assert scale_from_members([child], TODAY) == D("1.3")
    assert scale_from_members([], TODAY) == D("1.0")


@given(household=members)
def test_household_scale_is_at_least_one(household: list[Member]) -> None:
    assert scale_from_members(household, TODAY) >= 1


@given(household=members, extra=members)
def test_household_scale_never_drops_when_someone_moves_in(
    household: list[Member], extra: list[Member]
) -> None:
    assert scale_from_members(household + extra, TODAY) >= scale_from_members(household, TODAY)


# ── person_weight: OECD-modified, for members other than the user ──────────


@pytest.mark.parametrize(
    ("role", "age", "expected"),
    [
        ("adult", None, D("0.5")),
        ("adult", 64, D("0.5")),
        ("child", 0, D("0.3")),
        ("child", 13, D("0.3")),  # last year under 14
        ("child", 14, D("0.5")),  # 14 and over counts like an adult
        ("child", 17, D("0.5")),
    ],
)
def test_person_weight_oecd_modified(role: str, age: int | None, expected: Decimal) -> None:
    assert person_weight(role, age) == expected


@pytest.mark.parametrize(
    ("role", "age"),
    [("pet", None), ("", None), ("Adult", None), ("child", None), ("child", -1), ("adult", -5)],
)
def test_person_weight_rejects_invalid_members(role: str, age: int | None) -> None:
    # pets are a different fact type and never reach the scale; a child needs an age
    with pytest.raises(ValueError):
        person_weight(role, age)


# ── is_active: [valid_from, valid_to], None = open-ended ─────────────────────


@pytest.mark.parametrize(
    ("valid_from", "valid_to", "on_date", "expected"),
    [
        (None, None, TODAY, True),
        (TODAY, None, TODAY, True),
        (TODAY + timedelta(days=1), None, TODAY, False),
        (None, TODAY, TODAY, True),
        (None, TODAY - timedelta(days=1), TODAY, False),
        (TODAY, TODAY, TODAY, True),
    ],
)
def test_is_active_bounds_are_inclusive(
    valid_from: date | None, valid_to: date | None, on_date: date, expected: bool
) -> None:
    assert is_active(valid_from, valid_to, on_date) is expected


def test_is_active_rejects_window_ending_before_it_starts() -> None:
    with pytest.raises(ValueError):
        is_active(date(2026, 7, 31), date(2026, 7, 1), TODAY)
