"""Life-event tool handlers (A3 step 3; arch 6.6): planned events with a cost."""

from collections.abc import Mapping
from typing import Any

from app import clock
from app.agent.handlers.common import RunState, ToolContext
from app.agent.handlers.records import adder, check_money, record_id, updater
from app.agent.ports import RecordsPort, Services
from app.domain.enums import LifeEventStatus
from app.errors import DomainError

_IDS = ("event_id", "life_event_id", "id")


def _events(services: Services) -> RecordsPort:
    return services.life_events


def _check(data: Mapping[str, Any]) -> None:
    check_money(data, "est_cost", allow_zero=True)
    if data.get("date") is not None and data["date"] < clock.today():
        raise DomainError("invalid_date", "A planned event can't be in the past.", 422)


def _check_new(data: Mapping[str, Any]) -> None:
    _check(data)


add_life_event = adder(_events, "life_event", _check_new)
update_life_event = updater(_events, "life_event", _IDS, _check)


async def cancel_life_event(
    ctx: ToolContext, run: RunState, args: Mapping[str, Any]
) -> dict[str, Any]:
    rid = record_id(args, *_IDS)
    await ctx.services.life_events.get(ctx.user_id, rid)
    row = await ctx.services.life_events.update(
        ctx.user_id, rid, {"status": LifeEventStatus.CANCELLED}
    )
    return {"life_event": row, "_trigger_ref": {"life_event_id": rid}}
