"""Goal tool handlers (A3 step 3; arch 6.6, D17, D21): one active goal at a time."""

from collections.abc import Mapping
from typing import Any

from app import clock
from app.agent.handlers.common import RunState, ToolContext, changes, need_changes, to_jsonable
from app.domain.enums import GoalStatus
from app.domain.money import to_money
from app.errors import DomainError


def _check(amount: Any, deadline: Any) -> None:
    if amount is not None and to_money(amount) <= 0:
        raise DomainError("invalid_input", "The goal amount must be above 0.", 422)
    if deadline is not None and deadline <= clock.today():
        raise DomainError("invalid_deadline", "The goal deadline must be in the future.", 422)


def set_goal(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    if ctx.services.goals.active(ctx.user_id) is not None:
        raise DomainError(
            "goal_already_active", "A goal is already active: use update_goal to change it.", 409
        )
    _check(args["amount"], args["deadline"])
    goal = ctx.services.goals.create(
        ctx.user_id,
        {
            "amount": to_money(args["amount"]),
            "deadline": args["deadline"],
            "motivation": args.get("motivation"),
            "status": GoalStatus.ACTIVE,
        },
    )
    return {"goal": to_jsonable(goal), "_trigger_ref": {"goal_id": goal.id}}


def update_goal(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
    goal = ctx.services.goals.active(ctx.user_id)
    if goal is None:
        raise DomainError("no_active_goal", "There is no active goal: use set_goal.", 409)
    found = changes(args)
    need_changes(found, "goal")
    _check(found.get("amount"), found.get("deadline"))
    goal = ctx.services.goals.update(ctx.user_id, goal.id, found)
    return {"goal": to_jsonable(goal), "_trigger_ref": {"goal_id": goal.id}}
