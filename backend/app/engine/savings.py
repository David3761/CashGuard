"""Pots, expected receivables and payday auto-save (arch 6.7, D37). Pure, no DB, no clock."""

from collections.abc import Iterable
from datetime import date, timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from zoneinfo import ZoneInfo

from app.domain.enums import Direction, ReceivableStatus
from app.domain.models import FixedCost, IncomeSource, Receivable, TxView
from app.domain.money import to_money
from app.engine.calendar import days_in_month, occurrences, paydays_between

BUCHAREST = ZoneInfo("Europe/Bucharest")
CENT = Decimal("0.01")
P_REPAY_ON_TIME = Decimal("0.9")
P_REPAY_STEP = Decimal("0.1")
OVERDUE_STEP_DAYS = 14
SALARY_TOLERANCE = Decimal("0.20")
DAY_TOLERANCE = 3
NEXT_PAYDAY_SEARCH_DAYS = 62
OPEN_RECEIVABLES = frozenset({ReceivableStatus.OPEN, ReceivableStatus.REQUESTED})


def pot_contribution(
    target: Decimal, saved: Decimal, deadline: date | None, today: date, paydays: Iterable[int]
) -> Decimal:
    """(target − saved) per payday left in `(today, deadline]`, rounded up to the cent.

    No payday left before the deadline → the whole rest now. No deadline, deadline passed or
    target reached → 0.
    """
    remaining = target - saved
    if remaining <= 0 or deadline is None or deadline < today:
        return Decimal(0)
    left = len(paydays_between(paydays, today, deadline))
    return (remaining / left).quantize(CENT, rounding=ROUND_UP) if left else to_money(remaining)


def p_repay(expected_by: date, today: date) -> Decimal:
    """0.9 until `expected_by`, then −0.1 per full 14 days overdue, never below 0."""
    overdue = (today - expected_by).days
    if overdue < OVERDUE_STEP_DAYS:
        return P_REPAY_ON_TIME
    return max(Decimal(0), P_REPAY_ON_TIME - P_REPAY_STEP * (overdue // OVERDUE_STEP_DAYS))


def receivables_expected(receivables: Iterable[Receivable], today: date, deadline: date) -> Decimal:
    """Σ amount × p_repay of open/requested receivables expected by the deadline (inclusive)."""
    return to_money(
        sum(
            (
                r.amount * p_repay(r.expected_by, today)
                for r in receivables
                if r.status in OPEN_RECEIVABLES and r.expected_by <= deadline
            ),
            Decimal(0),
        )
    )


def _nearest_occurrence_gap(on: date, day_of_month: int) -> int:
    """Days between `on` and the closest date falling on `day_of_month` (previous, same or next month)."""
    gaps = []
    for shift in (-1, 0, 1):
        year, month = divmod(on.year * 12 + on.month - 1 + shift, 12)
        month += 1
        gaps.append(abs((date(year, month, min(day_of_month, days_in_month(year, month))) - on).days))
    return min(gaps)


def matches_recurring(
    amount: Decimal, on: date, expected_amount: Decimal, day_of_month: int, tolerance: Decimal
) -> bool:
    """`amount` within ±`tolerance` of `expected_amount` and `on` within ±3 days of `day_of_month`."""
    return abs(amount - expected_amount) <= tolerance * expected_amount and (
        _nearest_occurrence_gap(on, day_of_month) <= DAY_TOLERANCE
    )


def matching_income_source(tx: TxView, income_sources: Iterable[IncomeSource]) -> IncomeSource | None:
    """The income source a credit is the salary of (±20 % amount, ±3 days), if any (D37)."""
    if tx.direction != Direction.CREDIT:
        return None
    on = tx.occurred_at.astimezone(BUCHAREST).date()
    return next(
        (
            s
            for s in income_sources
            if matches_recurring(tx.amount, on, s.amount, s.day_of_month, SALARY_TOLERANCE)
        ),
        None,
    )


def auto_save_amount(
    *,
    still_to_save: Decimal,
    goal_deadline: date,
    balance: Decimal,
    today: date,
    income_days: Iterable[int],
    fixed_costs: Iterable[FixedCost],
    essentials_floor: Decimal,
) -> Decimal:
    """min(planned saving, what the balance can spare until the next payday), never negative (D37).

    planned saving = still_to_save / paydays left in `[today, deadline]` (today's salary is one of them).
    spare = balance − fixed costs due in `[today, next payday)` − essentials floor × days to the next payday.
    """
    if still_to_save <= 0 or goal_deadline < today:
        return Decimal("0.00")
    days = list(income_days)
    left = len(paydays_between(days, today - timedelta(days=1), goal_deadline))
    planned = still_to_save / left if left else still_to_save
    upcoming = paydays_between(days, today, today + timedelta(days=NEXT_PAYDAY_SEARCH_DAYS))
    next_payday = upcoming[0] if upcoming else today + timedelta(days=31)
    fixed_due = sum(
        (
            fc.amount
            * len(occurrences(fc.day_of_month, today - timedelta(days=1), next_payday - timedelta(days=1)))
            for fc in fixed_costs
        ),
        Decimal(0),
    )
    spare = balance - fixed_due - essentials_floor * (next_payday - today).days
    return max(Decimal(0), min(planned, spare)).quantize(CENT, rounding=ROUND_DOWN)
