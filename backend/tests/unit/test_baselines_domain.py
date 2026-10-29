"""E6 functions on F2 domain types: household scale from facts, baselines, essentials floor,
rescale."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.domain.enums import (
    Beneficiary,
    Category,
    Direction,
    FactStatus,
    FactType,
    HouseholdRole,
    Purpose,
)
from app.domain.models import Baseline, HouseholdMemberValue
from app.engine.baselines import (
    Priors,
    compute_baselines,
    essentials_floor,
    household_scale,
    rescale,
)
from tests.builders import fact, tx

D = Decimal
TODAY = date(2026, 6, 15)
BUCHAREST = ZoneInfo("Europe/Bucharest")
JULY = (date(2026, 7, 1), date(2026, 7, 31))

# test priors in data/priors.json's shape (C1); not the file's numbers
PRIORS: Priors = {
    "cities": [
        {"id": "bucuresti", "names": ["București"], "index": D("1.0")},
        {"id": "cluj", "names": ["Cluj"], "index": D("1.0")},
        {"id": "iasi", "names": ["Iași"], "index": D("0.85")},
    ],
    "default_city_index": D("1.0"),
    "categories": {
        "groceries": {"basket_median": D("70"), "monthly_mean": D("800"), "cv": D("0.25")},
        "transport": {"basket_median": D("15"), "monthly_mean": D("200"), "cv": D("0.3")},
        "health_pharmacy": {"basket_median": D("40"), "monthly_mean": D("100"), "cv": D("0.5")},
        "household_goods": {"basket_median": D("60"), "monthly_mean": D("120"), "cv": D("0.4")},
        "electronics": {"basket_median": D("300"), "monthly_mean": D("100"), "cv": D("0.8")},
        "income": {"basket_median": D("1"), "monthly_mean": D("1"), "cv": D("0.1")},
    },
}


def at(day: date, hour: int = 12) -> datetime:
    return datetime.combine(day, time(hour), tzinfo=BUCHAREST)


def groceries(effective: str, days_ago: int = 1, **over: Any) -> Any:
    when = at(TODAY - timedelta(days_ago))
    return tx(category=Category.GROCERIES, effective_amount=D(effective), occurred_at=when, **over)


def baselines_for(
    txs: list[Any], scale: str = "1.0", city: str | None = "București"
) -> dict[Category, Baseline]:
    return compute_baselines(txs, PRIORS, D(scale), city, TODAY)


# ── household_scale(facts, on_date) ──────────────────────────────────────────


def member(role: str, age: int | None = None, **over: Any) -> Any:
    return fact(
        type=FactType.HOUSEHOLD_MEMBER,
        value=HouseholdMemberValue(role=HouseholdRole(role), age=age),
        **over,
    )


IOANA_FACTS = [member("adult"), member("child", 7), member("child", 11)]


def test_household_scale_ioana_from_confirmed_facts() -> None:
    assert household_scale(IOANA_FACTS, TODAY) == D("2.1")


def test_household_scale_no_household_facts_is_the_user_alone() -> None:
    assert household_scale([], TODAY) == D("1.0")


def test_household_scale_ignores_hypotheses_rejected_and_other_fact_types() -> None:
    facts = [
        *IOANA_FACTS,
        member("child", 3, status=FactStatus.HYPOTHESIS),
        member("adult", status=FactStatus.REJECTED),
        fact(type=FactType.PET, value={"species": "dog"}),
    ]
    assert household_scale(facts, TODAY) == D("2.1")


@pytest.mark.parametrize(
    ("on_date", "expected"), [(date(2026, 7, 10), D("2.6")), (date(2026, 8, 1), D("2.1"))]
)
def test_household_scale_temporary_mother_in_july(on_date: date, expected: Decimal) -> None:
    mother = member("adult", 64, valid_from=JULY[0], valid_to=JULY[1])
    assert household_scale([*IOANA_FACTS, mother], on_date) == expected


# ── compute_baselines: blend with the prior ──────────────────────────────────


def test_no_history_gives_prior_times_scale_times_city_for_household_category() -> None:
    b = baselines_for([], scale="2.1", city="Iași")[Category.GROCERIES]
    assert b.n == 0
    assert b.expected_median == D("124.95")  # 70 x 2.1 x 0.85
    assert b.monthly_expected == D("1428.00")  # 800 x 2.1 x 0.85
    assert b.household_multiplier == D("2.1")


def test_five_transactions_give_the_midpoint_of_personal_and_prior() -> None:
    b = baselines_for([groceries("100", d) for d in range(1, 6)])[Category.GROCERIES]
    assert b.n == 5
    assert b.expected_median == D("85.00")  # (5·100 + 5·70) / 10


def test_long_history_is_close_to_personal() -> None:
    b = baselines_for([groceries("100", d) for d in range(1, 101)])[Category.GROCERIES]
    assert b.expected_median == D("98.57")  # (100·100 + 5·70) / 105
    assert b.personal_median == D("100.00")


def test_monthly_expected_blends_personal_monthly_rate_with_prior() -> None:
    # 10 x 100 lei over a 60-day span (earliest 59 days ago) → 1000 x 30.4375 / 60 per month
    txs = [groceries("100", d) for d in (59, 50, 40, 30, 25, 20, 15, 10, 5, 1)]
    assert baselines_for(txs)[Category.GROCERIES].monthly_expected == D("604.86")


def test_mad_zero_falls_back_to_quarter_of_expected_median() -> None:
    b = baselines_for([groceries("100", d) for d in range(1, 6)])[Category.GROCERIES]
    assert b.personal_mad == D("21.25")  # 0.25 x 85


def test_category_without_prior_uses_personal_history_only() -> None:
    books = [
        tx(category=Category.BOOKS, effective_amount=D("60"), occurred_at=at(TODAY - timedelta(3)))
    ]
    b = baselines_for(books)[Category.BOOKS]
    assert (b.n, b.expected_median, b.prior_median) == (1, D("60.00"), D("0.00"))


def test_non_household_category_is_never_scaled() -> None:
    b = baselines_for([], scale="2.1", city="Iași")[Category.ELECTRONICS]
    assert b.expected_median == D("300.00")
    assert b.household_multiplier == D("1")


@pytest.mark.parametrize(
    ("city", "expected"), [("Timișoara", D("70.00")), (None, D("70.00")), ("iasi", D("59.50"))]
)
def test_city_index_unknown_is_one_and_lookup_ignores_case_and_diacritics(
    city: str | None, expected: Decimal
) -> None:
    assert baselines_for([], city=city)[Category.GROCERIES].expected_median == expected


def test_spending_categories_only() -> None:
    assert Category.INCOME not in baselines_for([])


# ── compute_baselines: clean inputs (effective amounts, exclusions) ──────────


def test_shared_purchase_counts_with_its_effective_amount() -> None:
    b = baselines_for([groceries("100", amount=D("500"))])[Category.GROCERIES]
    assert b.personal_median == D("100.00")


@pytest.mark.parametrize(
    "over",
    [
        {"purpose": Purpose.PLANNED_EVENT},
        {"beneficiary": Beneficiary.OTHERS},
        {"beneficiary": Beneficiary.EMPLOYER},
        {"direction": Direction.CREDIT},
    ],
)
def test_excluded_transactions_do_not_count(over: dict[str, Any]) -> None:
    b = baselines_for([groceries("85"), groceries("900", **over)])[Category.GROCERIES]
    assert b.n == 1


def test_window_is_180_days_inclusive() -> None:
    b = baselines_for([groceries("85", 180), groceries("85", 181)])[Category.GROCERIES]
    assert b.n == 1


def test_day_is_taken_in_bucharest_time() -> None:
    # 21:30Z on 14 Jun = 00:30 on 15 Jun in Bucharest → inside; 21:30Z on 15 Jun = 16 Jun → after
    # today
    early = tx(
        category=Category.GROCERIES,
        occurred_at=datetime(2026, 6, 14, 21, 30, tzinfo=ZoneInfo("UTC")),
    )
    late = tx(
        category=Category.GROCERIES,
        occurred_at=datetime(2026, 6, 15, 21, 30, tzinfo=ZoneInfo("UTC")),
    )
    assert baselines_for([early, late])[Category.GROCERIES].n == 1


def test_compute_baselines_is_deterministic_and_rounded_to_cents() -> None:
    txs = [groceries(str(80 + d), d) for d in range(1, 30)]
    first, second = baselines_for(txs, scale="2.1"), baselines_for(txs, scale="2.1")
    assert first == second
    for b in first.values():
        for value in (
            b.expected_median,
            b.monthly_expected,
            b.prior_median,
            b.personal_median,
            b.personal_mad,
        ):
            assert value == value.quantize(D("0.01"))


@given(amounts=st.lists(st.decimals(min_value="0.01", max_value="5000", places=2), max_size=30))
def test_every_baseline_is_non_negative(amounts: list[Decimal]) -> None:
    txs = [groceries(str(a), i % 180 + 1) for i, a in enumerate(amounts)]
    for b in baselines_for(txs, scale="2.1").values():
        assert min(b.expected_median, b.monthly_expected, b.personal_mad, b.prior_median) >= 0


# ── essentials_floor and rescale ─────────────────────────────────────────────


def test_essentials_floor_matei_by_hand() -> None:
    # no history, alone in Bucharest: groceries 800 + transport 200 + pharmacy 100 + household goods
    # 120
    base = baselines_for([])
    assert essentials_floor(base, date(2026, 6, 1)) == D("40.67")  # 1220 / 30
    assert essentials_floor(base, date(2026, 7, 1)) == D("39.35")  # 1220 / 31


def test_essentials_floor_without_essential_categories_is_zero() -> None:
    assert essentials_floor({}, date(2026, 6, 1)) == D("0.00")


def test_rescale_multiplies_only_household_categories() -> None:
    old = baselines_for([groceries("140", d) for d in range(1, 11)], scale="2.1", city="Cluj")
    new = rescale(old, D("2.1"), D("2.6"))
    g_old, g_new = old[Category.GROCERIES], new[Category.GROCERIES]
    assert g_new.expected_median == (g_old.expected_median * D("2.6") / D("2.1")).quantize(
        D("0.01")
    )
    assert g_new.monthly_expected == (g_old.monthly_expected * D("2.6") / D("2.1")).quantize(
        D("0.01")
    )
    assert g_new.household_multiplier == D("2.6")
    assert new[Category.ELECTRONICS] == old[Category.ELECTRONICS]


def test_rescale_back_and_forth_is_stable_within_a_cent() -> None:
    old = baselines_for([], scale="2.1")
    back = rescale(rescale(old, D("2.1"), D("2.6")), D("2.6"), D("2.1"))
    assert abs(
        back[Category.GROCERIES].expected_median - old[Category.GROCERIES].expected_median
    ) <= D("0.01")


@pytest.mark.parametrize(
    ("old", "new"), [(D("0"), D("2.6")), (D("2.1"), D("0")), (D("-1"), D("1"))]
)
def test_rescale_rejects_non_positive_scales(old: Decimal, new: Decimal) -> None:
    with pytest.raises(ValueError, match="must be > 0"):
        rescale({}, old, new)
