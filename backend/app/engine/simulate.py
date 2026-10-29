"""What-if `simulate_plan` and solve mode (arch 6.7, D20, E5). Pure: works on a copy, saves nothing.

`changes` uses the tool's field names: goal_amount, deadline, add_events, remove_event_ids, income_delta,
fixed_cost_delta (monthly, + or −), weekday_weights, pin_days, buffer_pct, target_daily_budget (solve mode).
Solve mode bisects: the earliest deadline (up to 5 years) and the largest goal (same deadline) whose
daily budget today is at least the target. The daily budget isn't strictly monotonic in the deadline
(it jumps on paydays), so the deadline found is one where the day before misses the target.
"""

from collections.abc import Mapping
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from app.domain.models import FixedCost, IncomeSource, LifeEvent, UserContext
from app.domain.money import to_money
from app.domain.results import SimResult
from app.engine.baselines import essentials_floor
from app.engine.budget import compute_plan, plan_inputs
from app.engine.forecast import build_forecast_inputs, forecast
from app.errors import DomainError

SIM_PATHS = 2_000
SOLVE_HORIZON_DAYS = 5 * 365
WEIGHT_RANGE = (Decimal("0.5"), Decimal(3))
BUFFER_RANGE = (Decimal(0), Decimal("0.3"))
KNOWN = frozenset(
    {
        "goal_amount",
        "deadline",
        "add_events",
        "remove_event_ids",
        "income_delta",
        "fixed_cost_delta",
        "weekday_weights",
        "pin_days",
        "buffer_pct",
        "target_daily_budget",
    }
)
SIMULATED_ID = -1


def _invalid(message: str) -> DomainError:
    return DomainError("invalid_change", message)


def _money(value: Any) -> Decimal:
    return Decimal(str(value))


def _date(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value))


def apply_changes(ctx: UserContext, changes: Mapping[str, Any]) -> UserContext:
    """A copy of `ctx` with the hypothetical changes applied (validated like the real tools)."""
    unknown = set(changes) - KNOWN
    if unknown:
        raise _invalid(f"unknown change(s): {', '.join(sorted(unknown))}")
    if ctx.goal is None:
        raise DomainError("no_goal", "there is no active goal to simulate")
    update: dict[str, Any] = {}

    goal_update: dict[str, Any] = {}
    if "goal_amount" in changes:
        goal_update["amount"] = _money(changes["goal_amount"])
        if goal_update["amount"] <= 0:
            raise _invalid("goal_amount must be > 0")
    if "deadline" in changes:
        goal_update["deadline"] = _date(changes["deadline"])
    if goal_update:
        update["goal"] = ctx.goal.model_copy(update=goal_update)

    events = [e for e in ctx.life_events if e.id not in set(changes.get("remove_event_ids", ()))]
    for i, e in enumerate(changes.get("add_events", ())):
        cost = _money(e["est_cost"])
        if cost < 0:
            raise _invalid("est_cost must be ≥ 0")
        events.append(
            LifeEvent(id=SIMULATED_ID - i, name=str(e["name"]), date=_date(e["date"]), est_cost=cost)
        )
    update["life_events"] = events

    if changes.get("income_delta"):
        day = ctx.income_sources[0].day_of_month if ctx.income_sources else 1
        extra = IncomeSource(
            id=SIMULATED_ID, source="simulated", amount=_money(changes["income_delta"]), day_of_month=day
        )
        update["income_sources"] = [*ctx.income_sources, extra]
    if changes.get("fixed_cost_delta"):
        extra_cost = FixedCost(
            id=SIMULATED_ID, name="simulated", amount=_money(changes["fixed_cost_delta"]), day_of_month=1
        )
        update["fixed_costs"] = [*ctx.fixed_costs, extra_cost]

    prefs = ctx.plan_preferences
    prefs_update: dict[str, Any] = {}
    if "weekday_weights" in changes:
        weights = {k: _money(v) for k, v in changes["weekday_weights"].items()}
        if any(not WEIGHT_RANGE[0] <= w <= WEIGHT_RANGE[1] for w in weights.values()):
            raise _invalid("weekday weights must be 0.5–3")
        prefs_update["weekday_weights"] = {**prefs.weekday_weights, **weights}
    if "pin_days" in changes:
        pins = {_date(p["date"]): _money(p["amount"]) for p in changes["pin_days"]}
        prefs_update["pinned_days"] = {**prefs.pinned_days, **pins}
    if "buffer_pct" in changes:
        buffer = _money(changes["buffer_pct"])
        if not BUFFER_RANGE[0] <= buffer <= BUFFER_RANGE[1]:
            raise _invalid("buffer_pct must be 0–0.3")
        prefs_update["buffer_pct"] = buffer
    if prefs_update:
        update["plan_preferences"] = prefs.model_copy(update=prefs_update)
    return ctx.model_copy(update=update)


def _today_budget(ctx: UserContext, today: date, floor: Decimal, **goal: Any) -> Decimal:
    goal_ctx = ctx.model_copy(update={"goal": ctx.goal.model_copy(update=goal)}) if goal else ctx
    plan = compute_plan(plan_inputs(goal_ctx, today, floor), today)
    return plan.today_budget if plan is not None else Decimal(0)


def solve(ctx: UserContext, today: date, target: Decimal, *, essentials_floor: Decimal) -> dict[str, Any]:
    """Earliest deadline and largest goal giving a daily budget today of at least `target`."""
    if ctx.goal is None:
        raise DomainError("no_goal", "there is no active goal to solve for")
    floor = essentials_floor

    def deadline_ok(d: date) -> bool:
        return _today_budget(ctx, today, floor, deadline=d) >= target

    current = ctx.goal.deadline
    deadline_needed: date | None
    if deadline_ok(current):
        deadline_needed = current
    elif not deadline_ok(today + timedelta(days=SOLVE_HORIZON_DAYS)):
        deadline_needed = None
    else:
        lo, hi = current, today + timedelta(days=SOLVE_HORIZON_DAYS)  # lo misses, hi works
        while (hi - lo).days > 1:
            mid = lo + (hi - lo) / 2
            lo, hi = (lo, mid) if deadline_ok(mid) else (mid, hi)
        deadline_needed = hi

    def amount_ok(cents: int) -> bool:
        return _today_budget(ctx, today, floor, amount=Decimal(cents) / 100) >= target

    goal_cents = int(ctx.goal.amount * 100)
    amount_possible: Decimal | None
    if amount_ok(goal_cents):
        amount_possible = ctx.goal.amount
    elif not amount_ok(1):
        amount_possible = None
    else:
        lo_c, hi_c = 1, goal_cents  # lo works, hi misses
        while hi_c - lo_c > 1:
            mid_c = (lo_c + hi_c) // 2
            lo_c, hi_c = (mid_c, hi_c) if amount_ok(mid_c) else (lo_c, mid_c)
        amount_possible = to_money(Decimal(lo_c) / 100)

    reason = "target_not_reachable" if deadline_needed is None and amount_possible is None else None
    return {"deadline_needed": deadline_needed, "goal_amount_possible": amount_possible, "reason": reason}


def simulate(ctx: UserContext, today: date, changes: Mapping[str, Any], *, seed: int) -> SimResult:
    changed = apply_changes(ctx, changes)
    floor = essentials_floor(ctx.baselines, today)
    current_plan = compute_plan(plan_inputs(ctx, today, floor), today)
    plan = compute_plan(plan_inputs(changed, today, floor), today)
    if current_plan is None or plan is None:
        raise DomainError("no_goal", "there is no active goal to simulate")
    current_p = forecast(build_forecast_inputs(ctx, today), SIM_PATHS, seed).probability
    p = forecast(build_forecast_inputs(changed, today), SIM_PATHS, seed).probability
    target = changes.get("target_daily_budget")
    return SimResult(
        feasible=plan.feasible,
        today_budget=plan.today_budget,
        avg_daily_budget=to_money(sum((d.budget for d in plan.days), Decimal(0)) / len(plan.days)),
        probability=p,
        diff_vs_current={
            "today_budget": plan.today_budget - current_plan.today_budget,
            "probability": round(p - current_p, 4),
        },
        solve=solve(changed, today, _money(target), essentials_floor=floor) if target is not None else None,
    )
