"""Read-only tool handlers (A3 step 4; arch 6.6, D20): nothing here writes anything."""

from collections import defaultdict
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any

from app import clock
from app.agent.handlers.common import RunState, ToolContext, changes, pick, to_jsonable
from app.agent.handlers.transactions import get_transaction
from app.domain.enums import Direction
from app.errors import DomainError

__all__ = ["get_transaction"]

DEFAULT_DAYS = 14
MAX_DAYS = 92
MAX_ROWS = 50


def get_transactions(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    until = pick(args, "to_date", "to", "until", default=clock.today())
    since = pick(
        args, "from_date", "from_", "from", "since", default=until - timedelta(DEFAULT_DAYS)
    )
    if since > until:
        raise DomainError("invalid_input", "from must not be after to.", 422)
    if (until - since).days > MAX_DAYS:
        raise DomainError("invalid_input", f"Ask for at most {MAX_DAYS} days at a time.", 422)
    txs = ctx.services.transactions.list(ctx.user_id, since, until, args.get("category"))
    txs = sorted(txs, key=lambda t: t.occurred_at, reverse=True)
    return {
        "from": since.isoformat(),
        "to": until.isoformat(),
        "count": len(txs),
        "transactions": [to_jsonable(t) for t in txs[:MAX_ROWS]],
        "truncated": len(txs) > MAX_ROWS,
    }


def get_spending_summary(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    days = int(args.get("period_days") or 30)
    if not 1 <= days <= MAX_DAYS:
        raise DomainError("invalid_input", f"period_days must be 1..{MAX_DAYS}.", 422)
    until = clock.today()
    since = until - timedelta(days=days - 1)
    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for tx in ctx.services.transactions.list(ctx.user_id, since, until):
        if tx.direction is Direction.DEBIT:
            by_category[str(tx.category or "other")] += tx.effective_amount
    ranked = sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "from": since.isoformat(),
        "to": until.isoformat(),
        "total_effective": to_jsonable(sum(by_category.values(), Decimal("0.00"))),
        "by_category": [{"category": c, "effective": to_jsonable(a)} for c, a in ranked],
    }


def get_plan_status(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    return {"plan": to_jsonable(ctx.services.plans.latest(ctx.user_id))}


def get_goal_forecast(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "goal": to_jsonable(ctx.services.goals.active(ctx.user_id)),
        "forecast": to_jsonable(ctx.services.forecasts.latest(ctx.user_id)),
    }


def simulate_plan(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    found = changes(args)
    if not found:
        raise DomainError("nothing_to_simulate", "Give at least one change to simulate.", 422)
    result = ctx.engine.simulate_plan(ctx.db, ctx.user_id, found)
    return {"simulation": to_jsonable(result), "saved": False}


def suggest_savings_products(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    """The mock products ranked for this person: the goal horizon first, then the rate."""
    goal = ctx.services.goals.active(ctx.user_id)
    months = None if goal is None else max(0, (goal.deadline - clock.today()).days // 30)
    ranked = []
    for product in ctx.services.products.list():
        low, high = product.get("min_months", 0), product.get("max_months", 0)
        fits = months is None or low <= months <= high
        if months is None:
            reason = "no goal deadline yet: an instant-access product keeps options open"
            fits = product.get("liquidity") == "instant"
        elif fits:
            reason = f"fits a {months}-month horizon ({low}-{high} months)"
        else:
            reason = f"made for {low}-{high} months; the goal is {months} months away"
        ranked.append((not fits, -float(product.get("rate", 0)), product, reason))
    ranked.sort(key=lambda r: (r[0], r[1], str(r[2].get("id"))))
    return {
        "horizon_months": months,
        "products": [
            {**to_jsonable(p), "fits": not unfit, "reason": reason}
            for unfit, _, p, reason in ranked
        ],
    }
