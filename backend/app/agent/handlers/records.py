"""Shared create / update / remove for the plain per-user records (A3 step 3)."""

from collections.abc import Callable, Mapping
from typing import Any

from app.agent.handlers.common import Handler, RunState, ToolContext, changes, need_changes, pick
from app.agent.ports import RecordsPort, Services
from app.domain.money import to_money
from app.errors import DomainError

PortOf = Callable[[Services], RecordsPort]


def check_money(data: Mapping[str, Any], *fields: str, allow_zero: bool = False) -> None:
    for name in fields:
        if data.get(name) is None:
            continue
        amount = to_money(data[name])
        if amount < 0 or (amount == 0 and not allow_zero):
            raise DomainError("invalid_input", f"{name} must be above 0.", 422)


def check_day(data: Mapping[str, Any]) -> None:
    day = data.get("day_of_month")
    if day is not None and not 1 <= day <= 31:
        raise DomainError("invalid_input", "day_of_month must be 1..31.", 422)


def record_id(args: Mapping[str, Any], *names: str) -> int:
    value = pick(args, *names)
    if not isinstance(value, int):
        raise DomainError("invalid_input", f"Give the id ({names[0]}).", 422)
    return value


def adder(port: PortOf, what: str, check: Callable[[Mapping[str, Any]], None]) -> Handler:
    async def handler(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
        data = changes(args)
        check(data)
        row = await port(ctx.services).create(ctx.user_id, data)
        return {what: row, "_trigger_ref": {f"{what}_id": row["id"]}}

    return handler


def updater(
    port: PortOf, what: str, ids: tuple[str, ...], check: Callable[[Mapping[str, Any]], None]
) -> Handler:
    async def handler(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
        rid = record_id(args, *ids)
        records = port(ctx.services)
        await records.get(ctx.user_id, rid)  # not_found for another user's row
        found = changes(args, *ids)
        need_changes(found, what.replace("_", " "))
        check(found)
        row = await records.update(ctx.user_id, rid, found)
        return {what: row, "_trigger_ref": {f"{what}_id": rid}}

    return handler


def remover(port: PortOf, what: str, ids: tuple[str, ...]) -> Handler:
    async def handler(ctx: ToolContext, run: RunState, args: Mapping[str, Any]) -> dict[str, Any]:
        rid = record_id(args, *ids)
        records = port(ctx.services)
        await records.get(ctx.user_id, rid)
        await records.remove(ctx.user_id, rid)
        return {f"removed_{what}_id": rid, "_trigger_ref": {f"{what}_id": rid}}

    return handler
