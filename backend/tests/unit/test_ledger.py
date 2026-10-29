from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

pytest.importorskip("app.domain", reason="needs F2 app.domain (David G.)")

from app.domain.enums import Category, Direction, Purpose
from app.domain.models import Baseline, FixedCost

from app.engine.ledger import apply, counts_as_spent, estimate_own_share, ledger_day, reannotate_delta
from tests.builders import tx

D = Decimal
RENT = FixedCost(id=1, name="Chirie", amount=D("2000"), day_of_month=1)
JUNE_15 = datetime(2026, 6, 15, 10, 5, tzinfo=UTC)


def mega(effective: str = "500", **over: object) -> Any:
    return tx(amount=D("500"), effective_amount=D(effective), occurred_at=JUNE_15, **over)


def test_debit_moves_balance_by_amount_and_spent_by_effective() -> None:
    delta = apply(mega(), [RENT])
    assert (delta.day, delta.balance, delta.spent, delta.pot_saved) == (
        date(2026, 6, 15),
        D("-500"),
        D("500"),
        D("0"),
    )


def test_shared_purchase_spent_is_the_own_share_but_balance_the_full_amount() -> None:
    delta = apply(mega("100"), [RENT])
    assert (delta.balance, delta.spent) == (D("-500"), D("100"))


def test_salary_credit_raises_balance_and_is_never_spent() -> None:
    salary = tx(
        amount=D("7000"), effective_amount=D("7000"), direction=Direction.CREDIT, category=Category.INCOME
    )
    delta = apply(salary, [RENT])
    assert (delta.balance, delta.spent) == (D("7000"), D("0"))


def test_rent_matching_a_fixed_cost_is_not_spent() -> None:
    rent = tx(
        amount=D("2000"),
        effective_amount=D("2000"),
        category=Category.HOUSING_RENT,
        occurred_at=datetime(2026, 6, 1, 8, 0, tzinfo=UTC),
    )
    delta = apply(rent, [RENT])
    assert (delta.balance, delta.spent) == (D("-2000"), D("0"))


def test_pot_funded_transaction_is_not_spent_and_draws_from_the_pot() -> None:
    flight = tx(
        amount=D("900"),
        effective_amount=D("900"),
        purpose=Purpose.PLANNED_EVENT,
        pot_id=3,
        category=Category.TRAVEL,
        occurred_at=JUNE_15,
    )
    delta = apply(flight, [])
    assert (delta.balance, delta.spent, delta.pot_saved, delta.pot_id) == (D("-900"), D("0"), D("-900"), 3)


def test_ledger_day_is_the_bucharest_date() -> None:
    assert ledger_day(datetime(2026, 6, 14, 21, 30, tzinfo=UTC)) == date(2026, 6, 15)
    assert ledger_day(datetime(2026, 6, 14, 20, 59, tzinfo=UTC)) == date(2026, 6, 14)


def test_reannotation_500_to_100_lowers_spent_by_400_and_keeps_balance() -> None:
    delta = reannotate_delta(mega("500"), mega("100"), [RENT])
    assert (delta.day, delta.balance, delta.spent, delta.pot_saved) == (
        date(2026, 6, 15),
        D("0"),
        D("-400"),
        D("0"),
    )


def test_reannotation_to_planned_event_removes_spent_and_draws_from_the_pot() -> None:
    after = mega("500", purpose=Purpose.PLANNED_EVENT, pot_id=3)
    delta = reannotate_delta(mega("500"), after, [RENT])
    assert (delta.spent, delta.pot_saved, delta.pot_id) == (D("-500"), D("-500"), 3)


def test_reannotation_back_from_planned_event_refunds_the_pot() -> None:
    before = mega("500", purpose=Purpose.PLANNED_EVENT, pot_id=3)
    delta = reannotate_delta(before, mega("500"), [RENT])
    assert (delta.spent, delta.pot_saved, delta.pot_id) == (D("500"), D("500"), 3)


def test_reannotation_with_the_same_values_changes_nothing() -> None:
    delta = reannotate_delta(mega("100"), mega("100"), [RENT])
    assert (delta.balance, delta.spent, delta.pot_saved) == (D("0"), D("0"), D("0"))


def test_counts_as_spent_excludes_transfers_and_savings() -> None:
    assert not counts_as_spent(tx(category=Category.SAVINGS), [])
    assert not counts_as_spent(tx(category=Category.TRANSFERS), [])
    assert counts_as_spent(tx(category=Category.GROCERIES), [])


def baseline(expected: str) -> Baseline:
    return Baseline(
        category=Category.GROCERIES,
        personal_median=D(expected),
        personal_mad=D("25"),
        n=20,
        prior_median=D("70"),
        household_multiplier=D("1"),
        expected_median=D(expected),
        monthly_expected=D("800"),
    )


@pytest.mark.parametrize(
    ("amount", "expected_median", "own"),
    [(D("500"), "85", D("85.00")), (D("60"), "85", D("60.00")), (D("500"), None, D("500.00"))],
)
def test_estimate_own_share_is_the_baseline_clamped_to_the_amount(
    amount: Decimal, expected_median: str | None, own: Decimal
) -> None:
    b = baseline(expected_median) if expected_median else None
    assert estimate_own_share(amount, b) == own
