"""E7 wrapper on F2 types: anomaly_features(tx, baseline, history, monthly_disposable)."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

pytest.importorskip("app.domain", reason="needs F2 app.domain (David G.)")

from app.domain.enums import Category
from app.domain.models import Baseline, FixedCost, IncomeSource

from app.engine.anomaly import anomaly_features, monthly_disposable
from tests.builders import tx

D = Decimal
NOW = datetime(2026, 6, 15, 10, 5, tzinfo=UTC)
MEGA = 7
GROCERIES = Baseline(
    category=Category.groceries,
    personal_median=D("85"),
    personal_mad=D("25"),
    n=40,
    prior_median=D("70"),
    household_multiplier=D("1"),
    expected_median=D("85"),
    monthly_expected=D("1400"),
)


def mega(amount: str, when: datetime = NOW, merchant: int | None = MEGA) -> Any:
    return tx(
        amount=D(amount),
        effective_amount=D(amount),
        merchant_id=merchant,
        category=Category.groceries,
        occurred_at=when,
    )


def test_matei_mega_500_from_domain_objects() -> None:
    history = [mega("80", NOW - timedelta(days=d)) for d in (1, 3, 6)]
    f = anomaly_features(mega("500"), GROCERIES, history, D("4385"))
    assert f.z == pytest.approx(11.196, abs=0.001)
    assert (f.stat, f.novelty, f.materiality) == (1.0, 0.0, 1.0)


def test_the_transaction_itself_and_later_ones_are_not_history() -> None:
    current = mega("500")
    later = mega("90", NOW + timedelta(days=2))
    f = anomaly_features(current, GROCERIES, [current, later], D("4385"))
    assert f.novelty == 1.0  # nothing seen before it


def test_new_merchant_in_a_known_category_is_half_novel() -> None:
    history = [mega("80", NOW - timedelta(days=10), merchant=99)]
    assert anomaly_features(mega("90"), GROCERIES, history, D("4385")).novelty == 0.5


def test_no_baseline_scores_any_spending_as_unusual() -> None:
    f = anomaly_features(mega("50"), None, [], D("4385"))
    assert f.stat == 1.0


def test_monthly_disposable_is_income_minus_fixed_costs() -> None:
    income = [IncomeSource(id=1, source="Salariu", amount=D("7000"), day_of_month=10)]
    fixed = [
        FixedCost(id=1, name="Chirie", amount=D("2000"), day_of_month=1),
        FixedCost(id=2, name="Utilități", amount=D("615"), day_of_month=15),
    ]
    assert monthly_disposable(income, fixed) == D("4385")
