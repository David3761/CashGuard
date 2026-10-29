from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

pytest.importorskip("app.domain", reason="needs F2 app.domain (David G.)")

from app.domain.enums import Category, ReceivableStatus, SignatureEffect
from app.domain.models import Receivable, Signature

from app.engine.forecast import build_forecast_inputs, forecast
from app.engine.options import PROBABILITY_FLOOR, cuttable_categories, drivers, options
from app.engine.stats import stable_seed
from tests.builders import tx
from tests.unit.test_forecast import GOAL, TODAY, at, history, matei_ctx

D = Decimal
SEED = stable_seed(1, TODAY, 1)
CONCERTS = Signature(id=1, fact_id=1, effect=SignatureEffect.PROTECTS, category=Category.ENTERTAINMENT)
OCCASIONAL = {
    Category.GROCERIES: 1400,
    Category.RESTAURANTS: 900,
    Category.FOOD_DELIVERY: 500,
    Category.ENTERTAINMENT: 300,
}


def varied_history() -> list[Any]:
    """Monthly totals that change from month to month (a bootstrap needs some spread)."""
    txs = history({})
    for month, factor in zip(range(2, 6), (0.7, 1.0, 1.4, 0.9)):
        for category, amount in OCCASIONAL.items():
            value = D(str(round(amount * factor)))
            txs.append(
                tx(
                    category=category,
                    amount=value,
                    effective_amount=value,
                    occurred_at=at(date(2026, month, 15)),
                )
            )
    return txs


def goal_ctx(amount: str, **over: object) -> Any:
    """Matei with a varied history; 16 000 → P ≈ 0.93, 17 000 → ≈ 0.76, 18 500 → ≈ 0.3 (seeded)."""
    over.setdefault("goal", replace(GOAL, amount=D(amount)))
    return matei_ctx(transactions=varied_history(), **over)


def probability(c: object) -> float:
    return forecast(build_forecast_inputs(c, TODAY), seed=SEED).probability


# ── drivers ──────────────────────────────────────────────────────────────────


def test_cuttable_categories_exclude_essential_household_and_protected() -> None:
    cats = {
        Category.GROCERIES,
        Category.RESTAURANTS,
        Category.ENTERTAINMENT,
        Category.KIDS,
        Category.FOOD_DELIVERY,
    }
    assert cuttable_categories(cats, [CONCERTS]) == {Category.RESTAURANTS, Category.FOOD_DELIVERY}


def test_drivers_are_non_negative_sorted_and_skip_protected() -> None:
    c = goal_ctx("17500", signatures=[CONCERTS])
    result = drivers(build_forecast_inputs(c, TODAY), c.signatures, seed=SEED)
    categories = {d.category for d in result}
    assert categories == {Category.RESTAURANTS, Category.FOOD_DELIVERY}
    assert all(d.pp_per_100_lei >= 0 for d in result)
    assert [d.pp_per_100_lei for d in result] == sorted((d.pp_per_100_lei for d in result), reverse=True)
    assert result[0].pp_per_100_lei > 0


# ── options ──────────────────────────────────────────────────────────────────


def test_no_options_when_the_probability_is_fine() -> None:
    c = goal_ctx("16000")
    current = probability(c)
    assert current >= PROBABILITY_FLOOR
    assert options(c, TODAY, current=current, previous=current, seed=SEED) == []


def test_options_when_the_probability_is_low_are_at_most_three_and_each_better() -> None:
    r = Receivable(
        id=1,
        amount=D("400"),
        debtor_label="colegi",
        expected_by=date(2026, 7, 1),
        status=ReceivableStatus.OPEN,
    )
    c = goal_ctx("18500", receivables=[r])
    current = probability(c)
    assert current < PROBABILITY_FLOOR
    result = options(c, TODAY, current=current, previous=None, seed=SEED)
    assert [o.kind for o in result] == ["count_receivables", "move_deadline", "reduce_category"]
    assert all(o.probability > current for o in result)


def test_options_after_a_big_drop_even_above_the_floor() -> None:
    c = goal_ctx("17000")
    current = probability(c)
    assert PROBABILITY_FLOOR <= current < 1
    assert options(c, TODAY, current=current, previous=current + 0.11, seed=SEED)
    assert options(c, TODAY, current=current, previous=current + 0.10, seed=SEED) == []  # exactly 10 pp: no


def test_no_deadline_option_for_a_hard_goal() -> None:
    c = goal_ctx("18500", goal=replace(GOAL, amount=D("18500"), hard_deadline=True))
    kinds = {o.kind for o in options(c, TODAY, current=probability(c), previous=None, seed=SEED)}
    assert "move_deadline" not in kinds


def test_reduction_option_never_cuts_more_than_a_quarter_of_the_baseline_and_never_protected() -> None:
    c = goal_ctx("18500", signatures=[CONCERTS])
    cuts = [
        o
        for o in options(c, TODAY, current=probability(c), previous=None, seed=SEED)
        if o.kind == "reduce_category"
    ]
    assert cuts
    for o in cuts:
        assert o.params["category"] != Category.ENTERTAINMENT
        assert o.params["amount_per_month"] <= o.params["baseline_per_month"] * D("0.25")


def test_option_labels_are_i18n_keys_with_params() -> None:
    c = goal_ctx("18500")
    for o in options(c, TODAY, current=probability(c), previous=None, seed=SEED):
        assert o.label_key == f"option.{o.kind}"
        assert isinstance(o.params, dict)
