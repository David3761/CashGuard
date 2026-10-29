"""The engine's §15 shells (arch 15.1, danutu): S0 stubs with the exact signatures.

Built by David G. on danutu's behalf (team rule D42: we build what we need and log it in
HANDOFFS.md). danutu's E3 (`apply_transaction`, `on_annotation_changed`), E4 (`recompute_plan`),
E5 (`simulate_plan`), E6 (`recompute_baselines`), E8 (`forecast_goal`) and E10 (`auto_save`,
`own_share_estimate`) replace the bodies. Stub behaviour (Danutu.md S0):
- `recompute_plan` returns a fixed plan, `forecast_goal` a probability of 0.78;
- `apply_transaction` moves the balance by `amount` and the day's spent by `effective_amount`
  (`ledger_delta`; the DB write waits for bomboe's B3, so the shell writes nothing yet);
- `auto_save` returns None; `own_share_estimate` the whole amount; the others are no-ops.

The pure `anomaly_features` / `household_scale` are not here: they live in `anomaly.py` /
`baselines.py`. `db` is typed `Any` until bomboe's session exists.
"""

from datetime import date
from decimal import Decimal
from typing import Any, Final

from app import clock
from app.domain.enums import Category, Direction
from app.domain.models import DomainModel, TxView
from app.domain.money import Money

STUB_TODAY_BUDGET: Final = Decimal("150.00")
STUB_PROBABILITY: Final = 0.78
"""The demo's opening number (arch 16.2 Scene A: "78%")."""

# ── TODO(F2): placeholders with F2's planned names (F2.md steps 6 and 7). Replace each with the ──
# ── import from app.domain (models / results) when F2 lands; the fields here are a subset. ──────


class DayBudget(DomainModel):  # TODO(F2): app.domain.results.DayBudget
    date: date
    budget: Money
    pinned: bool = False


class PlanSummary(DomainModel):  # TODO(F2): app.domain.results.PlanSummary
    version: int
    feasible: bool
    today_budget: Money
    previous_today_budget: Money | None = None
    next_7_days: tuple[DayBudget, ...] = ()
    reason: str | None = None


class Forecast(DomainModel):  # TODO(F2): app.domain.results.Forecast
    probability: float
    previous_probability: float | None = None
    last_week_probability: float | None = None
    p10: Money
    p50: Money
    p90: Money
    expected_reach_date: date | None = None


class SimDiff(DomainModel):  # TODO(F2): app.domain.results.SimDiff
    today_budget: Money
    probability: float


class SimResult(DomainModel):  # TODO(F2): app.domain.results.SimResult
    feasible: bool
    today_budget: Money
    avg_daily_budget: Money
    probability: float
    diff_vs_current: SimDiff


class Baseline(DomainModel):  # TODO(F2): app.domain.models.Baseline
    category: Category
    expected_median: Money
    monthly_expected: Money


class Transfer(DomainModel):  # TODO(F2): app.domain.models.Transfer
    id: int
    amount: Money


# ── pure helper ──────────────────────────────────────────────────────────────────────────────


def ledger_delta(tx: TxView) -> tuple[Decimal, Decimal]:
    """(balance change, day-spent change) of one transaction: a debit moves the balance by
    -amount and the day's spent by +effective_amount; a credit moves the balance by +amount and
    is never spent. (E3 adds planned_event, fixed costs and pots.)"""
    if tx.direction == Direction.CREDIT:
        return tx.amount, Decimal("0.00")
    return -tx.amount, tx.effective_amount


# ── the §15 functions ────────────────────────────────────────────────────────────────────────


def apply_transaction(db: Any, user_id: int, tx_id: int) -> None:
    """Stub of E3: `ledger_delta` is the rule; no write until bomboe's services exist."""
    return None


def on_annotation_changed(db: Any, user_id: int, tx_id: int, old: TxView, new: TxView) -> None:
    """Stub of E3: a no-op (the real one moves the day's spent by the effective-amount change)."""
    return None


def recompute_baselines(db: Any, user_id: int) -> dict[str, Baseline]:
    """Stub of E6: no baselines."""
    return {}


def recompute_plan(
    db: Any, user_id: int, reason: str, trigger_ref: dict[str, Any] | None = None
) -> PlanSummary:
    """Stub of E4: a fixed, feasible plan of 150 lei a day (version 1), saving nothing."""
    return PlanSummary(
        version=1,
        feasible=True,
        today_budget=STUB_TODAY_BUDGET,
        next_7_days=(DayBudget(date=clock.today(), budget=STUB_TODAY_BUDGET),),
        reason=reason,
    )


def forecast_goal(db: Any, user_id: int, plan_version: int) -> Forecast:
    """Stub of E8: probability 0.78 (the demo's opening number), saving nothing."""
    return Forecast(
        probability=STUB_PROBABILITY,
        p10=Decimal("8500.00"),
        p50=Decimal("10200.00"),
        p90=Decimal("11800.00"),
    )


def simulate_plan(db: Any, user_id: int, changes: dict[str, Any]) -> SimResult:
    """Stub of E5: the current stub plan, unchanged by `changes` (saves nothing)."""
    return SimResult(
        feasible=True,
        today_budget=STUB_TODAY_BUDGET,
        avg_daily_budget=STUB_TODAY_BUDGET,
        probability=STUB_PROBABILITY,
        diff_vs_current=SimDiff(today_budget=Decimal("0.00"), probability=0.0),
    )


def own_share_estimate(db: Any, user_id: int, tx: TxView) -> Decimal:
    """Stub of E10: with no count or amount given, the whole amount is the user's."""
    return tx.amount


def auto_save(db: Any, user_id: int, income_tx_id: int) -> Transfer | None:
    """Stub of E10: never auto-saves."""
    return None
