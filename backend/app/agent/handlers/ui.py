"""UI tool handlers (A3 step 4): quick replies on the reply; marking an event handled (D22: both
are allowed in proactive runs)."""

from collections.abc import Mapping
from typing import Any

from app.agent.handlers.common import RunState, ToolContext
from app.errors import DomainError

MAX_QUICK_REPLIES = 5


async def show_quick_replies(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    options = [str(o).strip() for o in args.get("options") or [] if str(o).strip()]
    unique = list(dict.fromkeys(options))
    if not 1 <= len(unique) <= MAX_QUICK_REPLIES or any(len(o) > 80 for o in unique):
        raise DomainError(
            "invalid_input", "Give 1 to 5 distinct options of at most 80 characters.", 422
        )
    run.quick_replies = unique
    return {"quick_replies": unique}


async def mark_event_handled(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    event = await ctx.services.agent_events.mark_handled(ctx.user_id, args["event_id"])
    return {"event_id": event["id"], "status": event["status"]}
