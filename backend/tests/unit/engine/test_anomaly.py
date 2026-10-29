"""E7 minimum: anomaly features (arch 5.3.4 step 4)."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.domain.enums import Category
from app.domain.models import Baseline, TxView
from app.engine.anomaly import anomaly_features
from tests.builders import TODAY, at
from tests.builders import tx as base_tx

_ids = iter(range(100, 10**6))


def tx(**overrides: object) -> TxView:
    return base_tx(id=next(_ids), **overrides)


def baseline(category: Category, median: str, mad: str) -> Baseline:
    return Baseline.model_validate(
        {
            "category": category,
            "personal_median": median,
            "personal_mad": mad,
            "n": 20,
            "prior_median": median,
            "household_multiplier": 1,
            "expected_median": median,
            "monthly_expected": median,
        }
    )


GROCERIES = baseline(Category.GROCERIES, "85", "25")
MATEI_DISPOSABLE = Decimal(4385)  # 7 000 - 2 000 - 350 - 60 - 25 - 180


def test_matei_worked_example() -> None:
    history = [tx(occurred_at=at(TODAY - timedelta(days=2)))]
    features = anomaly_features(
        tx(amount=Decimal(500), effective_amount=Decimal(500)), GROCERIES, history, MATEI_DISPOSABLE
    )
    assert features.z == pytest.approx(11.2, abs=0.05)
    assert (features.stat, features.novelty, features.materiality) == (1.0, 0.0, 1.0)


def test_below_the_median_is_stat_zero() -> None:
    features = anomaly_features(
        tx(amount=Decimal(60), effective_amount=Decimal(60)), GROCERIES, (), MATEI_DISPOSABLE
    )
    assert features.stat == 0


def test_novelty_levels_and_the_90_day_boundary() -> None:
    new = tx(merchant_raw="SHOP&GO", merchant="Shop&Go", merchant_id="shop_go")
    seen_90 = tx(occurred_at=at(TODAY - timedelta(days=90)))
    seen_91 = tx(occurred_at=at(TODAY - timedelta(days=91)))
    assert anomaly_features(new, GROCERIES, [seen_90], MATEI_DISPOSABLE).novelty == 0.5
    assert anomaly_features(new, GROCERIES, [seen_91], MATEI_DISPOSABLE).novelty == 1.0
    assert anomaly_features(tx(), GROCERIES, [seen_90], MATEI_DISPOSABLE).novelty == 0.0
    assert anomaly_features(tx(), GROCERIES, [seen_91], MATEI_DISPOSABLE).novelty == 1.0


def test_no_disposable_means_material() -> None:
    assert anomaly_features(tx(), GROCERIES, (), Decimal(0)).materiality == 1.0


def test_mad_zero_falls_back_to_a_quarter_of_the_median() -> None:
    flat = baseline(Category.GROCERIES, "100", "0")
    features = anomaly_features(
        tx(amount=Decimal(200), effective_amount=Decimal(200)), flat, (), MATEI_DISPOSABLE
    )
    assert features.z == pytest.approx(100 / (1.4826 * 25))


@pytest.mark.parametrize("amount", ["50", "85", "500", "99999"])
def test_outputs_in_unit_range(amount: str) -> None:
    f = anomaly_features(
        tx(amount=Decimal(amount), effective_amount=Decimal(amount)),
        GROCERIES,
        (),
        MATEI_DISPOSABLE,
    )
    assert all(0 <= v <= 1 for v in (f.stat, f.novelty, f.materiality))
