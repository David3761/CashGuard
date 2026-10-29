"""Day-level signals → agent_event drafts (arch 6.7, F3/F5, E11). Pure.

Thresholds (🟡 danutu to confirm, then final):
- warning: spent > 0.9 x budget; overspend: spent > budget (only the stronger one fires)
- under (ledger status at close): spent < 0.5 x budget
- underspend_week (at Sunday's close): the week's spending ≤ 80 % of the week's budget
- category_cap: this ISO week's spending in a capped category reaches 80 % / 100 % of the cap;
  one event a day (unique per type and date), keeping the highest level
- infeasible_plan: the new plan is infeasible and the previous one wasn't
- goal_completed: the goal pot reaches the active goal (once: the goal is then completed)
Every type at most once per day, and never one that already exists for that day.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Protocol

from app.domain.enums import AgentEventType
from app.domain.results import PlanResult, SignalDraft
from app.domain.user_context import UserContext
from app.engine.ledger import counts_as_spent, ledger_day

WARNING_SHARE = Decimal("0.9")
UNDER_SHARE = Decimal("0.5")
WEEK_UNDER_SHARE = Decimal("0.8")
CAP_LEVELS = ((Decimal(1), 100), (Decimal("0.8"), 80))
SUNDAY = 6


class LedgerDay(Protocol):
    @property
    def date(self) -> date: ...
    @property
    def budget(self) -> Decimal: ...
    @property
    def spent(self) -> Decimal: ...


def day_status(spent: Decimal, budget: Decimal, *, closed: bool) -> str:
    """`day_ledger.status`: ok | warning | overspent | under ("under" only once the day is
    closed)."""
    if spent > budget:
        return "overspent"
    if spent > WARNING_SHARE * budget:
        return "warning"
    if closed and spent < UNDER_SHARE * budget:
        return "under"
    return "ok"


def _cap_signal(ctx: UserContext, today: date) -> dict[str, Any] | None:
    caps = ctx.plan_preferences.category_caps
    if not caps:
        return None
    week_start = today - timedelta(days=today.weekday())
    spent: dict[Any, Decimal] = {}
    for t in ctx.transactions:
        if (
            t.category in caps
            and week_start <= ledger_day(t.occurred_at) <= today
            and counts_as_spent(t, ctx.fixed_costs)
        ):
            spent[t.category] = spent.get(t.category, Decimal(0)) + t.effective_amount
    best: dict[str, Any] | None = None
    for category, cap in caps.items():
        ratio = spent.get(category, Decimal(0)) / cap
        level = next((lvl for share, lvl in CAP_LEVELS if ratio >= share), None)
        if level is not None and (best is None or (level, ratio) > (best["level"], best["ratio"])):
            best = {
                "category": category,
                "level": level,
                "ratio": ratio,
                "spent": spent[category],
                "cap": cap,
            }
    return best


def detect_signals(
    ctx: UserContext,
    ledger_today: LedgerDay,
    plan: PlanResult | None,
    prev_forecast: Any,
    forecast: Any,
    *,
    week: Sequence[LedgerDay] = (),
    at_close: bool = False,
) -> list[SignalDraft]:
    today = ledger_today.date
    drafts: dict[AgentEventType, dict[str, Any]] = {}
    status = day_status(ledger_today.spent, ledger_today.budget, closed=at_close)
    if status in ("warning", "overspent"):
        kind = AgentEventType.OVERSPEND if status == "overspent" else AgentEventType.WARNING
        drafts[kind] = {
            "spent": ledger_today.spent,
            "budget": ledger_today.budget,
            "over": ledger_today.spent - ledger_today.budget,
        }

    if at_close and today.weekday() == SUNDAY and week:
        spent = sum((d.spent for d in week), Decimal(0))
        budget = sum((d.budget for d in week), Decimal(0))
        if budget > 0 and spent <= WEEK_UNDER_SHARE * budget:
            drafts[AgentEventType.UNDERSPEND_WEEK] = {"spent": spent, "budget": budget}

    cap = _cap_signal(ctx, today)
    if cap is not None:
        drafts[AgentEventType.CATEGORY_CAP] = cap

    previous_feasible = ctx.plan is None or ctx.plan.feasible
    if plan is not None and not plan.feasible and previous_feasible:
        drafts[AgentEventType.INFEASIBLE_PLAN] = {"infeasible_days": len(plan.infeasible_days)}

    goal, pot = ctx.goal, ctx.goal_pot
    if (
        goal is not None
        and pot is not None
        and goal.status == "active"
        and pot.saved >= goal.amount
    ):
        drafts[AgentEventType.GOAL_COMPLETED] = {"goal_id": goal.id, "saved": pot.saved}

    existing = {(e.type, e.event_date) for e in ctx.agent_events}
    return [
        SignalDraft(type=kind, date=today, payload=payload)
        for kind, payload in drafts.items()
        if (kind, today) not in existing
    ]
