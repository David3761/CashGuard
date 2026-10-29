"""Read-only tool handlers (A3 step 4; arch 6.6, D20): nothing here writes anything."""

from collections import defaultdict
from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any

from app import clock
from app.agent.handlers.common import RunState, ToolContext, changes, pick, to_jsonable
from app.agent.handlers.transactions import get_transaction
from app.context import products
from app.domain.enums import Direction
from app.errors import DomainError

__all__ = ["get_transaction"]

DEFAULT_DAYS = 14
MAX_DAYS = 92
MAX_ROWS = 50


async def get_transactions(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    until = pick(args, "to_date", "to", "until", default=clock.today())
    since = pick(
        args, "from_date", "from_", "from", "since", default=until - timedelta(DEFAULT_DAYS)
    )
    if since > until:
        raise DomainError("invalid_input", "from must not be after to.", 422)
    if (until - since).days > MAX_DAYS:
        raise DomainError("invalid_input", f"Ask for at most {MAX_DAYS} days at a time.", 422)
    txs = await ctx.services.transactions.list(ctx.user_id, since, until, args.get("category"))
    txs = sorted(txs, key=lambda t: t.occurred_at, reverse=True)
    return {
        "from": since.isoformat(),
        "to": until.isoformat(),
        "count": len(txs),
        "transactions": [to_jsonable(t) for t in txs[:MAX_ROWS]],
        "truncated": len(txs) > MAX_ROWS,
    }


async def get_spending_summary(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    days = int(args.get("period_days") or 30)
    if not 1 <= days <= MAX_DAYS:
        raise DomainError("invalid_input", f"period_days must be 1..{MAX_DAYS}.", 422)
    until = clock.today()
    since = until - timedelta(days=days - 1)
    by_category: dict[str, Decimal] = defaultdict(lambda: Decimal("0.00"))
    for tx in await ctx.services.transactions.list(ctx.user_id, since, until):
        if tx.direction is Direction.DEBIT:
            by_category[str(tx.category or "other")] += tx.effective_amount
    ranked = sorted(by_category.items(), key=lambda kv: (-kv[1], kv[0]))
    return {
        "from": since.isoformat(),
        "to": until.isoformat(),
        "total_effective": to_jsonable(sum(by_category.values(), Decimal("0.00"))),
        "by_category": [{"category": c, "effective": to_jsonable(a)} for c, a in ranked],
    }


async def get_plan_status(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    return {"plan": to_jsonable(await ctx.services.plans.latest(ctx.user_id))}


async def get_goal_forecast(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "goal": to_jsonable(await ctx.services.goals.active(ctx.user_id)),
        "forecast": to_jsonable(await ctx.services.forecasts.latest(ctx.user_id)),
    }


async def simulate_plan(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    found = changes(args)
    if not found:
        raise DomainError("nothing_to_simulate", "Give at least one change to simulate.", 422)
    result = await ctx.engine.simulate_plan(ctx.db, ctx.user_id, found)
    return {"simulation": to_jsonable(result), "saved": False}


async def suggest_savings_products(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    """The mock products ranked for this person by C12 (`context.products`): the goal horizon,
    the set amount and how steady the income is; `why_for_you` in the user's language."""
    s, uid = ctx.services, ctx.user_id
    needs = products.needs_from(
        await s.goals.active(uid),
        await s.income_sources.list(uid),
        await s.life_facts.list_active(uid),
        clock.today(),
    )
    ranked = products.rank_offers(needs, await s.products.list())
    return {
        "horizon_months": needs.horizon_months,
        "stable_income": needs.stable_income,
        "products": [
            {
                "id": r.product.id,
                "name": r.product.name,
                "kind": r.product.kind.value,
                "rate": float(r.product.rate),
                "liquidity": r.product.liquidity.value,
                "min_months": r.product.min_months,
                "max_months": r.product.max_months,
                "mock": r.mock,
                "rank": rank,
                "score": r.score,
                "fits": r.fits,
                "reason_key": r.reason_key,
                "why_for_you": r.why(ctx.language),
            }
            for rank, r in enumerate(ranked, start=1)
        ],
    }
