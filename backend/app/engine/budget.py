"""Daily budget engine (arch 6.7, E2). Pure, no DB, no clock.

Decisions (arch 6.7 "Engine definitions"):
- Horizon: every day in `[today, goal.deadline]`.
- Income dated today is already in the balance once processed: paydays count from tomorrow.
  Fixed costs work the same way: a cost due today counts as paid.
- `available` starts from the balance at the start of the day (`balance + spent_today`), so spending
  during the day doesn't shrink today's own budget; the next recompute (close-day) moves it to the rest.
- The buffer is a share of a positive `available` only.
- Each unpinned day gets `rest × weight / Σ weights`, rounded down to the cent; the rounding residual goes
  to the last unpinned day, so the budgets add up exactly to `free_money`.
- No goal → no plan (`None`); a deadline before today → `DomainError("deadline_passed")`.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal

from app.domain.enums import PotKind, PotStatus
from app.domain.models import FixedCost, Goal, IncomeSource, LifeEvent, PlanPreferences, Pot, Receivable
from app.domain.user_context import UserContext
from app.domain.money import to_money
from app.domain.results import DayBudget, PlanResult
from app.engine.calendar import iter_days, occurrences, paydays_between
from app.engine.ledger import counts_as_spent, ledger_day
from app.engine.savings import pot_contribution, receivables_expected
from app.errors import DomainError

CENT = Decimal("0.01")
ZERO = Decimal(0)
WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DEFAULT_WEIGHT = Decimal(1)
NEXT_DAYS = 7


@dataclass(frozen=True)
class PlanInputs:
    goal: Goal | None
    goal_saved: Decimal
    balance: Decimal
    spent_today: Decimal
    income_sources: tuple[IncomeSource, ...]
    fixed_costs: tuple[FixedCost, ...]
    events: tuple[LifeEvent, ...]  # planned life events
    pots: tuple[Pot, ...]  # active non-goal pots
    receivables: tuple[Receivable, ...]
    preferences: PlanPreferences
    essentials_floor: Decimal


# ── the money terms ──────────────────────────────────────────────────────────


def expected_income(sources: Iterable[IncomeSource], today: date, deadline: date) -> Decimal:
    """Σ income occurrences in `(today, deadline]`."""
    return sum((s.amount * len(occurrences(s.day_of_month, today, deadline)) for s in sources), ZERO)


def fixed_remaining(costs: Iterable[FixedCost], today: date, deadline: date) -> Decimal:
    """Σ fixed-cost occurrences not paid yet, in `(today, deadline]`."""
    return sum((c.amount * len(occurrences(c.day_of_month, today, deadline)) for c in costs), ZERO)


def events_remaining(
    events: Iterable[LifeEvent], pots: Iterable[Pot], today: date, deadline: date
) -> Decimal:
    """Σ est_cost of planned events in `[today, deadline]` that no active pot covers."""
    covered = {p.life_event_id for p in pots if p.life_event_id is not None and p.status == PotStatus.ACTIVE}
    return sum(
        (
            e.est_cost
            for e in events
            if e.status == "planned" and today <= e.date <= deadline and e.id not in covered
        ),
        ZERO,
    )


def pot_contributions_remaining(
    pots: Iterable[Pot], sources: Iterable[IncomeSource], today: date, deadline: date
) -> Decimal:
    """What still goes into event / custom pots before the goal deadline.

    A pot ending by the deadline needs its whole rest; one ending later only its contributions on the
    paydays inside the horizon.
    """
    days = [s.day_of_month for s in sources]
    total = ZERO
    for p in pots:
        if p.status != PotStatus.ACTIVE or p.kind == PotKind.GOAL:
            continue
        rest = max(ZERO, p.target - p.saved)
        if p.deadline is None or p.deadline <= deadline:
            total += rest
        else:
            per_payday = pot_contribution(p.target, p.saved, p.deadline, today, days)
            total += min(rest, per_payday * len(paydays_between(days, today, deadline)))
    return total


def still_to_save(goal_amount: Decimal, saved: Decimal) -> Decimal:
    return max(ZERO, goal_amount - saved)


def available(inputs: PlanInputs, today: date) -> Decimal:
    """balance (start of day) + income + receivables − fixed − events − pot contributions, to the deadline."""
    if inputs.goal is None:
        return ZERO
    deadline = inputs.goal.deadline
    return (
        inputs.balance
        + inputs.spent_today
        + expected_income(inputs.income_sources, today, deadline)
        + receivables_expected(inputs.receivables, today, deadline)
        - fixed_remaining(inputs.fixed_costs, today, deadline)
        - events_remaining(inputs.events, inputs.pots, today, deadline)
        - pot_contributions_remaining(inputs.pots, inputs.income_sources, today, deadline)
    )


# ── the daily split ──────────────────────────────────────────────────────────


def _weight(prefs: PlanPreferences, d: date) -> Decimal:
    return Decimal(prefs.weekday_weights.get(WEEKDAYS[d.weekday()], DEFAULT_WEIGHT))


def _split(days: list[date], rest: Decimal, prefs: PlanPreferences) -> dict[date, Decimal]:
    unpinned = [d for d in days if d not in prefs.pinned_days]
    if not unpinned:
        return {}
    weights = {d: _weight(prefs, d) for d in unpinned}
    total_weight = sum(weights.values(), ZERO)
    shares = {d: (rest * weights[d] / total_weight).quantize(CENT, rounding=ROUND_FLOOR) for d in unpinned}
    shares[unpinned[-1]] += rest - sum(shares.values(), ZERO)
    return shares


def compute_plan(inputs: PlanInputs, today: date) -> PlanResult | None:
    goal = inputs.goal
    if goal is None:
        return None
    if goal.deadline < today:
        raise DomainError("deadline_passed", f"the goal deadline {goal.deadline} is before {today}")
    days = iter_days(today, goal.deadline)
    prefs = inputs.preferences
    avail = to_money(available(inputs, today))
    to_save = still_to_save(goal.amount, inputs.goal_saved)
    free = to_money(avail - to_save - prefs.buffer_pct * max(avail, ZERO))
    pins = {d: to_money(prefs.pinned_days[d]) for d in days if d in prefs.pinned_days}
    rest = free - sum(pins.values(), ZERO)
    shares = _split(days, rest, prefs)
    budgets = [
        DayBudget(date=d, budget=pins.get(d, shares.get(d, ZERO)), weight=_weight(prefs, d), pinned=d in pins)
        for d in days
    ]
    below_floor = [b.date for b in budgets if not b.pinned and b.budget < inputs.essentials_floor]
    return PlanResult(
        today_budget=budgets[0].budget,
        days=budgets,
        next_7_days=budgets[1 : 1 + NEXT_DAYS],
        feasible=rest >= 0 and not below_floor,
        infeasible_days=below_floor,
        available=avail,
        free_money=free,
        still_to_save=to_save,
    )


# ── from the user context ────────────────────────────────────────────────────


def plan_inputs(ctx: UserContext, today: date, essentials_floor: Decimal) -> PlanInputs:
    """PlanInputs from the read model (B4): the goal pot is the goal; other active pots are event pots."""
    goal_pot_id = ctx.goal_pot.id if ctx.goal_pot is not None else None
    spent_today = sum(
        (
            t.effective_amount
            for t in ctx.transactions
            if ledger_day(t.occurred_at) == today and counts_as_spent(t, ctx.fixed_costs)
        ),
        ZERO,
    )
    return PlanInputs(
        goal=ctx.goal,
        goal_saved=ctx.goal_pot.saved if ctx.goal_pot is not None else ZERO,
        balance=ctx.account.current_balance,
        spent_today=spent_today,
        income_sources=tuple(ctx.income_sources),
        fixed_costs=tuple(ctx.fixed_costs),
        events=tuple(ctx.life_events),
        pots=tuple(p for p in ctx.pots if p.id != goal_pot_id and p.kind != PotKind.GOAL),
        receivables=tuple(ctx.receivables),
        preferences=ctx.plan_preferences,
        essentials_floor=essentials_floor,
    )
