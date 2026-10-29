"""Pot tool handlers (A3 step 3; arch 6.6, F13). The engine sets `monthly_contribution` (E10)
in the D18 recompute that follows each of these."""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from app import clock
from app.agent.handlers.common import RunState, ToolContext, changes, need_changes, to_jsonable
from app.domain.enums import PotStatus
from app.domain.models import Pot
from app.domain.money import to_money
from app.errors import DomainError


def _check_deadline(deadline: Any) -> None:
    if deadline is not None and deadline < clock.today():
        raise DomainError("invalid_deadline", "The deadline must not be in the past.", 422)


def _check_target(target: Any) -> None:
    if target is not None and to_money(target) <= 0:
        raise DomainError("invalid_input", "The pot target must be above 0.", 422)


async def _active_pot(ctx: ToolContext, pot_id: int) -> Pot:
    pot = await ctx.services.pots.get(ctx.user_id, pot_id)
    if pot.status is not PotStatus.ACTIVE:
        raise DomainError("pot_not_active", f"Pot {pot.id} is {pot.status}.", 409)
    return pot


def _result(pot: Pot) -> dict[str, Any]:
    return {"pot": to_jsonable(pot), "_trigger_ref": {"pot_id": pot.id}}


async def create_pot(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    _check_target(args["target"])
    _check_deadline(args.get("deadline"))
    if args.get("life_event_id") is not None:
        await ctx.services.life_events.get(ctx.user_id, args["life_event_id"])  # the user's event
    pot = await ctx.services.pots.create(
        ctx.user_id,
        {
            "name": args["name"],
            "kind": args["kind"],
            "target": to_money(args["target"]),
            "saved": Decimal("0.00"),
            "deadline": args.get("deadline"),
            "life_event_id": args.get("life_event_id"),
            "status": PotStatus.ACTIVE,
        },
    )
    return _result(pot)


async def update_pot(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    pot = await _active_pot(ctx, args["pot_id"])
    found = changes(args, "pot_id")
    need_changes(found, "pot")
    _check_target(found.get("target"))
    _check_deadline(found.get("deadline"))
    return _result(await ctx.services.pots.update(ctx.user_id, pot.id, found))


async def close_pot(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    pot = await _active_pot(ctx, args["pot_id"])
    return _result(await ctx.services.pots.close(ctx.user_id, pot.id))


async def link_transaction_to_pot(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    tx = await ctx.services.transactions.get(ctx.user_id, args["transaction_id"])
    pot = await _active_pot(ctx, args["pot_id"])
    tx = await ctx.services.transactions.set_pot(ctx.user_id, tx.id, pot.id)
    run.pushes.append(("transaction.annotated", {"transaction_id": tx.id, "pot_id": pot.id}))
    return {
        "transaction_id": tx.id,
        "pot_id": pot.id,
        "_trigger_ref": {"transaction_id": tx.id, "pot_id": pot.id},
    }
