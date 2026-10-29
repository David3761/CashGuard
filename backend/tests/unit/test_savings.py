from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

pytest.importorskip("app.domain", reason="needs F2 app.domain (David G.)")

from app.domain.enums import Direction, ReceivableStatus
from app.domain.models import FixedCost, IncomeSource, Receivable

from app.engine.calendar import paydays_between
from app.engine.savings import (
    auto_save_amount,
    matches_recurring,
    matching_income_source,
    p_repay,
    pot_contribution,
    receivables_expected,
)
from tests.builders import tx

D = Decimal
TODAY = date(2026, 6, 15)
DEADLINE = date(2026, 12, 31)
SALARY = IncomeSource(id=1, source="Salariu", amount=D("7000"), day_of_month=10)
RENT = FixedCost(id=1, name="Chirie", amount=D("2000"), day_of_month=1)


def receivable(
    amount: str, expected_by: date, status: ReceivableStatus = ReceivableStatus.open
) -> Receivable:
    return Receivable(id=1, amount=D(amount), debtor_label="colegi", expected_by=expected_by, status=status)


# ── pot_contribution ─────────────────────────────────────────────────────────


def test_pot_contribution_vacation_pot_example() -> None:
    # 3 000 by 15 Aug, from 15 Jun, salary on the 10th → 10 Jul, 10 Aug → 1 500 per payday
    assert pot_contribution(D("3000"), D("0"), date(2026, 8, 15), TODAY, [10]) == D("1500.00")


def test_pot_contribution_rounds_up_so_the_target_is_reached() -> None:
    # 1 000 over 3 paydays: 333.34 each (333.33 × 3 would miss a cent)
    assert pot_contribution(D("1000"), D("0"), date(2026, 9, 15), TODAY, [10]) == D("333.34")


@pytest.mark.parametrize(
    ("saved", "deadline", "expected"),
    [
        (D("3000"), date(2026, 8, 15), D("0")),  # already saved
        (D("3500"), date(2026, 8, 15), D("0")),  # more than the target
        (D("0"), date(2026, 6, 14), D("0")),  # deadline passed
        (D("0"), None, D("0")),  # no deadline, no schedule
    ],
)
def test_pot_contribution_nothing_to_do(saved: Decimal, deadline: date | None, expected: Decimal) -> None:
    assert pot_contribution(D("3000"), saved, deadline, TODAY, [10]) == expected


def test_pot_contribution_no_payday_left_asks_for_the_whole_rest_now() -> None:
    assert pot_contribution(D("800"), D("200"), date(2026, 7, 5), TODAY, [10]) == D("600.00")


@given(
    target=st.decimals(min_value=1, max_value=50_000, places=2),
    days=st.integers(min_value=1, max_value=400),
)
def test_pot_contribution_times_paydays_covers_the_target(target: Decimal, days: int) -> None:
    deadline = TODAY + timedelta(days=days)
    per_payday = pot_contribution(target, D("0"), deadline, TODAY, [10])
    paydays = max(1, len(paydays_between([10], TODAY, deadline)))
    assert per_payday * paydays >= target


# ── p_repay and receivables_expected ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("days_overdue", "expected"),
    [
        (-5, D("0.9")),
        (0, D("0.9")),
        (13, D("0.9")),
        (14, D("0.8")),
        (27, D("0.8")),
        (28, D("0.7")),
        (140, D("0")),
    ],
)
def test_p_repay_drops_a_tenth_per_full_fortnight(days_overdue: int, expected: Decimal) -> None:
    assert p_repay(TODAY - timedelta(days=days_overdue), TODAY) == expected


def test_receivables_expected_demo_400_not_overdue_is_360() -> None:
    assert receivables_expected([receivable("400", TODAY + timedelta(14))], TODAY, DEADLINE) == D("360.00")


def test_receivables_expected_four_weeks_overdue_is_280() -> None:
    assert receivables_expected([receivable("400", TODAY - timedelta(28))], TODAY, DEADLINE) == D("280.00")


def test_receivables_expected_after_the_deadline_counts_zero() -> None:
    assert receivables_expected([receivable("400", DEADLINE + timedelta(1))], TODAY, DEADLINE) == D("0.00")


def test_receivables_expected_on_the_deadline_counts() -> None:
    assert receivables_expected([receivable("400", DEADLINE)], TODAY, DEADLINE) == D("360.00")


@pytest.mark.parametrize("status", [ReceivableStatus.paid, ReceivableStatus.cancelled])
def test_receivables_expected_ignores_closed_receivables(status: ReceivableStatus) -> None:
    assert receivables_expected([receivable("400", TODAY, status)], TODAY, DEADLINE) == D("0.00")


def test_receivables_expected_counts_requested() -> None:
    r = receivable("100", TODAY, ReceivableStatus.requested)
    assert receivables_expected([r, receivable("400", TODAY)], TODAY, DEADLINE) == D("450.00")


# ── salary matching: ±20 % amount and ±3 days ────────────────────────────────


@pytest.mark.parametrize(
    ("amount", "on", "expected"),
    [
        (D("7000"), date(2026, 7, 10), True),
        (D("8400"), date(2026, 7, 10), True),  # +20 % exactly
        (D("8400.01"), date(2026, 7, 10), False),
        (D("5600"), date(2026, 7, 10), True),  # −20 % exactly
        (D("5599.99"), date(2026, 7, 10), False),
        (D("7000"), date(2026, 7, 13), True),  # +3 days
        (D("7000"), date(2026, 7, 14), False),
        (D("7000"), date(2026, 7, 7), True),  # −3 days
        (D("7000"), date(2026, 7, 6), False),
    ],
)
def test_matches_recurring_boundaries(amount: Decimal, on: date, expected: bool) -> None:
    assert matches_recurring(amount, on, D("7000"), 10, D("0.20")) is expected


def test_matches_recurring_across_month_end() -> None:
    # salary "on the 1st" paid on 30 June, rent "on the 31st" paid on 1 March after a short February
    assert matches_recurring(D("1000"), date(2026, 6, 30), D("1000"), 1, D("0.20"))
    assert matches_recurring(D("1000"), date(2027, 3, 1), D("1000"), 31, D("0.20"))


def test_matching_income_source_needs_a_credit() -> None:
    salary_day = datetime(2026, 7, 10, 7, 0, tzinfo=UTC)
    credit = tx(
        amount=D("7000"), effective_amount=D("7000"), direction=Direction.credit, occurred_at=salary_day
    )
    debit = tx(
        amount=D("7000"), effective_amount=D("7000"), direction=Direction.debit, occurred_at=salary_day
    )
    assert matching_income_source(credit, [SALARY]) == SALARY
    assert matching_income_source(debit, [SALARY]) is None
    assert matching_income_source(credit, []) is None


# ── auto_save_amount (D37) ───────────────────────────────────────────────────


def auto_save(
    balance: str, still: str = "4800", today: date = date(2026, 7, 10), floor: str = "40"
) -> Decimal:
    return auto_save_amount(
        still_to_save=D(still),
        goal_deadline=DEADLINE,
        balance=D(balance),
        today=today,
        income_days=[10],
        fixed_costs=[RENT],
        essentials_floor=D(floor),
    )


def test_auto_save_planned_saving_counts_todays_payday() -> None:
    # 10 Jul … 10 Dec = 6 paydays incl. today → 4 800 / 6 = 800; plenty of balance
    assert auto_save("9000") == D("800.00")


def test_auto_save_cap_when_the_balance_is_low() -> None:
    # until 10 Aug: rent 2 000 (1 Aug) + 31 days × 40 = 1 240 → cap = 3 900 − 3 240 = 660
    assert auto_save("3900") == D("660.00")


def test_auto_save_never_negative() -> None:
    assert auto_save("1000") == D("0.00")


@pytest.mark.parametrize("still", ["0", "-50"])
def test_auto_save_goal_reached_is_zero(still: str) -> None:
    assert auto_save("9000", still=still) == D("0.00")


def test_auto_save_deadline_passed_is_zero() -> None:
    assert auto_save("9000", today=date(2027, 1, 10)) == D("0.00")


@given(balance=st.decimals(min_value=-5000, max_value=50_000, places=2))
def test_auto_save_is_between_zero_and_the_balance(balance: Decimal) -> None:
    amount = auto_save(str(balance))
    assert D("0") <= amount <= max(balance, D("0"))
