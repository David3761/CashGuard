"""E6 minimum: household scale and blended baselines (arch 5.3.5, D50, D51)."""

import json
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.config import BACKEND_DIR
from app.domain.enums import Beneficiary, Category, FactStatus, FactType, HouseholdRole, Persistence
from app.domain.models import LifeFact, TxView
from app.engine.baselines import children_count, city_index, compute_baselines, household_scale
from tests.builders import TODAY, at, fact
from tests.builders import tx as base_tx

_ids = iter(range(100, 10**6))


def tx(**overrides: object) -> TxView:
    return base_tx(id=next(_ids), **overrides)


def member(fact_id: int, role: HouseholdRole, age: int | None, **overrides: object) -> LifeFact:
    value: dict[str, object] = {"role": role} | ({"age": age} if age is not None else {})
    return fact(FactType.HOUSEHOLD_MEMBER, id=fact_id, value=value, **overrides)


PRIORS = json.loads((BACKEND_DIR / "data" / "priors.json").read_text(encoding="utf-8"))


def test_scale_alone_couple_family() -> None:
    assert household_scale((), TODAY) == 1
    assert household_scale((member(1, HouseholdRole.ADULT, 30),), TODAY) == Decimal("1.5")
    family = (
        member(1, HouseholdRole.ADULT, 40),
        member(2, HouseholdRole.CHILD, 7),
        member(3, HouseholdRole.CHILD, 11),
    )
    assert household_scale(family, TODAY) == Decimal("2.1")
    assert children_count(family, TODAY) == 2


def test_a_14_year_old_counts_half() -> None:
    assert household_scale((member(1, HouseholdRole.CHILD, 14),), TODAY) == Decimal("1.5")
    assert household_scale((member(1, HouseholdRole.CHILD, 13),), TODAY) == Decimal("1.3")


def test_temporary_member_only_inside_window() -> None:
    family = (
        member(1, HouseholdRole.ADULT, 40),
        member(2, HouseholdRole.CHILD, 7),
        member(3, HouseholdRole.CHILD, 11),
        member(
            4,
            HouseholdRole.ADULT,
            65,
            persistence=Persistence.TEMPORARY,
            valid_from=date(2026, 7, 1),
            valid_to=date(2026, 7, 31),
        ),
    )
    assert household_scale(family, date(2026, 7, 10)) == Decimal("2.6")
    assert household_scale(family, date(2026, 7, 31)) == Decimal("2.6")
    assert household_scale(family, date(2026, 8, 1)) == Decimal("2.1")


def test_unconfirmed_members_are_ignored() -> None:
    hypo = member(1, HouseholdRole.ADULT, 30, status=FactStatus.HYPOTHESIS)
    assert household_scale((hypo,), TODAY) == 1


def test_city_index() -> None:
    assert city_index(PRIORS, "Iasi") == Decimal("0.85")
    assert city_index(PRIORS, "Cluj-Napoca") == 1
    assert city_index(PRIORS, "Timbuktu") == 1
    assert city_index(PRIORS, None) == 1


def test_new_user_starts_from_the_scaled_prior() -> None:
    out = compute_baselines((), PRIORS, Decimal("2.1"), "Cluj", TODAY)
    assert out[Category.GROCERIES].expected_median == Decimal("147.00")  # 70 x 2.1
    assert out[Category.ELECTRONICS].expected_median == Decimal("250.00")  # not scaled
    assert Category.KIDS not in out  # D50: no children → no kids prior
    assert Category.HOUSING_RENT not in out  # D51: no prior, no history


def test_kids_prior_is_per_child() -> None:
    out = compute_baselines((), PRIORS, Decimal("2.1"), "Cluj", TODAY, children=2)
    assert out[Category.KIDS].monthly_expected == Decimal("700.00")


def test_blend_n5_is_the_midpoint() -> None:
    history = [
        tx(occurred_at=at(TODAY - timedelta(days=d)), amount=130, effective_amount=130)
        for d in range(5)
    ]
    out = compute_baselines(history, PRIORS, Decimal(1), "București", TODAY)
    assert out[Category.GROCERIES].expected_median == Decimal("100.00")  # (130 + 70) / 2
    # MAD 0 is stored with the 0.25 x expected-median fallback (danutu E6, merged_notes 🟡)
    assert out[Category.GROCERIES].personal_mad == Decimal("25.00")


def test_clean_inputs_and_180_day_bound() -> None:
    history = [
        tx(occurred_at=at(TODAY - timedelta(days=180)), amount=Decimal(500),
           effective_amount=Decimal(100)),
        tx(occurred_at=at(TODAY - timedelta(days=181)), amount=900, effective_amount=900),
        tx(occurred_at=at(TODAY), amount=900, effective_amount=900, beneficiary=Beneficiary.OTHERS),
    ]  # fmt: skip
    out = compute_baselines(history, PRIORS, Decimal(1), None, TODAY)
    assert out[Category.GROCERIES].n == 1
    assert out[Category.GROCERIES].personal_median == Decimal("100.00")


@pytest.mark.parametrize("scale", [Decimal(1), Decimal("2.6")])
def test_baselines_are_never_negative(scale: Decimal) -> None:
    out = compute_baselines((), PRIORS, scale, None, TODAY)
    assert all(b.expected_median >= 0 and b.monthly_expected >= 0 for b in out.values())
