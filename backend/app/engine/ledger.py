"""Ledger rules: how one transaction moves the balance, the day's "spent" and a pot (E3). Pure.

- The balance moves by the full `amount` (debit −, credit +).
- "Spent" counts `effective_amount` of debits, except fixed costs (±10 %, ±3 days of a `fixed_costs` row),
  pot-funded spending (`planned_event`) and money moved to transfers / savings. Credits are never spent.
- A pot-funded transaction lowers `pot.saved` by its `amount`.
- The ledger day is `occurred_at` in Bucharest time.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.enums import Category, Direction, Purpose
from app.domain.models import Baseline, FixedCost, TxView
from app.domain.money import to_money
from app.engine.savings import matches_recurring

BUCHAREST = ZoneInfo("Europe/Bucharest")
FIXED_COST_TOLERANCE = Decimal("0.10")
NEVER_SPENT = frozenset({Category.income, Category.transfers, Category.savings})
ZERO = Decimal(0)


@dataclass(frozen=True)
class LedgerDelta:
    day: date
    balance: Decimal
    spent: Decimal
    pot_saved: Decimal
    pot_id: int | None


def ledger_day(occurred_at: datetime) -> date:
    return occurred_at.astimezone(BUCHAREST).date()


def is_fixed_cost(tx: TxView, fixed_costs: Iterable[FixedCost]) -> bool:
    on = ledger_day(tx.occurred_at)
    return any(
        matches_recurring(tx.amount, on, fc.amount, fc.day_of_month, FIXED_COST_TOLERANCE)
        for fc in fixed_costs
    )


def _pot_funded(tx: TxView) -> bool:
    return tx.pot_id is not None and tx.purpose == Purpose.planned_event


def counts_as_spent(tx: TxView, fixed_costs: Iterable[FixedCost]) -> bool:
    """True when the transaction's own share belongs in the day's variable spending."""
    return (
        tx.direction == Direction.debit
        and tx.category not in NEVER_SPENT
        and tx.purpose != Purpose.planned_event
        and not is_fixed_cost(tx, fixed_costs)
    )


def _spent(tx: TxView, fixed_costs: Iterable[FixedCost]) -> Decimal:
    return tx.effective_amount if counts_as_spent(tx, fixed_costs) else ZERO


def _pot_draw(tx: TxView) -> Decimal:
    return -tx.amount if _pot_funded(tx) else ZERO


def apply(tx: TxView, fixed_costs: Iterable[FixedCost]) -> LedgerDelta:
    """The changes one newly processed transaction makes."""
    fixed = list(fixed_costs)
    balance = -tx.amount if tx.direction == Direction.debit else tx.amount
    return LedgerDelta(ledger_day(tx.occurred_at), balance, _spent(tx, fixed), _pot_draw(tx), tx.pot_id)


def reannotate_delta(before: TxView, after: TxView, fixed_costs: Iterable[FixedCost]) -> LedgerDelta:
    """What changes when a processed transaction is re-annotated: never the balance."""
    fixed = list(fixed_costs)
    pot_id = after.pot_id if _pot_funded(after) else before.pot_id
    return LedgerDelta(
        ledger_day(after.occurred_at),
        ZERO,
        _spent(after, fixed) - _spent(before, fixed),
        _pot_draw(after) - _pot_draw(before),
        pot_id,
    )


def estimate_own_share(amount: Decimal, baseline: Baseline | None) -> Decimal:
    """Own share when the user gave no count or amount: the usual basket, never more than the amount."""
    return to_money(min(amount, baseline.expected_median) if baseline is not None else amount)
