"""/sim/* (arch F7, 9.2; B10). Only mounted when SIM_MODE=true; needs a logged-in user."""

from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Response
from pydantic import AwareDatetime, BaseModel, Field

from app import clock, events
from app.api import schemas as s
from app.api.deps import CurrentUser
from app.api.views import plan_out
from app.config import get_settings
from app.db.seed import persona_list, realm_subs, seed_all
from app.db.session import unit_of_work
from app.domain.enums import Category
from app.errors import DomainError
from app.pipeline import day_jobs
from app.pipeline.processor import process_user, users_with_work
from app.services import ledger, notifications, plans, users
from app.services.ingest import ingest
from app.sim import scenarios
from app.sim.clock_store import SimClock
from app.ws import manager

router = APIRouter(prefix="/sim", tags=["sim"])


def sim_clock() -> SimClock:
    current = clock.get_clock()
    if not isinstance(current, SimClock):
        current = SimClock(clock.today())
        clock.set_clock(current)
    return current


class SimTransactionIn(BaseModel):
    scenario_id: str | None = None
    merchant_raw: str | None = None
    amount: Decimal | None = None
    mcc: str | None = None
    category: Category | None = None
    items: list[dict[str, Any]] | None = None
    occurred_at: AwareDatetime | None = None
    persona: str | None = None


class JumpIn(BaseModel):
    days: int = Field(ge=1, le=60)


async def _persona_user(persona: str) -> int:
    sub = realm_subs().get(persona)
    async with unit_of_work() as db:
        user = await users.get_by_sub(db, sub) if sub else None
    if user is None:
        raise DomainError("persona_not_found", f"No seeded persona {persona!r}.", status=404)
    return user.id


async def _inject(user_id: int, payload: dict[str, Any]) -> int:
    async with unit_of_work() as db:
        tx_id = await ingest(db, user_id, payload)
    await process_user(user_id, "sim")
    return tx_id


@router.post("/transaction")
async def sim_transaction(body: SimTransactionIn, user: CurrentUser) -> dict[str, int]:
    """Inject one transaction (a scenario or a raw one) and run the pipeline now."""
    if body.scenario_id:
        scenario = scenarios.load(body.scenario_id)
        payload = {
            k: scenario.get(k) for k in ("merchant_raw", "amount", "mcc", "category", "items")
        }
        payload["occurred_at"] = scenarios.occurred_at(clock.today(), scenario)
        persona = body.persona or scenario.get("persona")
    else:
        payload = body.model_dump(exclude={"scenario_id", "persona"}, exclude_none=True)
        payload.setdefault("occurred_at", clock.now())
        persona = body.persona
    target = await _persona_user(persona) if persona else user.id
    return {"transaction_id": await _inject(target, payload)}


@router.get("/personas")
async def personas(_: CurrentUser) -> dict[str, list[dict[str, str]]]:
    return {"personas": persona_list()}


async def _next_day() -> None:
    day = clock.today()
    for entry in scenarios.scripted_day(day):
        payload = {k: v for k, v in entry.items() if k not in ("persona", "day_offset", "time")}
        payload["occurred_at"] = scenarios.occurred_at(day, entry)
        await _inject(await _persona_user(entry["persona"]), payload)
    for user_id in await users_with_work():
        await process_user(user_id, "sim")
    for job in day_jobs.day_sequence(day):
        await day_jobs.run_for_all(job, day)
    async with unit_of_work() as db:
        await sim_clock().advance(db, 1)
    await day_jobs.run_for_all(day_jobs.Job.PREEMPTIVE, clock.today())


@router.post("/next-day")
async def next_day(user: CurrentUser) -> dict[str, Any]:
    closed = clock.today()
    await _next_day()
    async with unit_of_work() as db:
        day = await ledger.get(db, user.id, closed)
        plan = await plans.latest(db, user.id)
        unread = await notifications.list_all(db, user.id, unread_only=True)
        return {
            "date": clock.today().isoformat(),
            "ledger": day.model_dump(mode="json") if day else None,
            "plan": (await plan_out(db, user.id, plan, clock.today())).model_dump(mode="json")
            if plan
            else None,
            "notifications": [
                s.NotificationOut(
                    **n.model_dump(include=set(s.NotificationOut.model_fields))
                ).model_dump(mode="json")
                for n in unread
            ],
        }


@router.post("/jump")
async def jump(body: JumpIn, user: CurrentUser) -> dict[str, Any]:
    for _ in range(body.days):
        await _next_day()
    async with unit_of_work() as db:
        plan = await plans.latest(db, user.id)
        return {
            "date": clock.today().isoformat(),
            "plan": (await plan_out(db, user.id, plan, clock.today())).model_dump(mode="json")
            if plan
            else None,
        }


@router.post("/reset", status_code=204)
async def reset(_: CurrentUser) -> Response:
    """Every persona back to its seed state; the clock back to SIM_START_DATE."""
    async with unit_of_work() as db:
        seeded = await seed_all(db, reset_first=True)
        await sim_clock().set(db, get_settings().SIM_START_DATE)
        latest = {uid: await plans.latest(db, uid) for uid in seeded.values()}
    for uid, plan in latest.items():
        if plan is not None:
            await manager.push(uid, events.plan_updated(plan))
    return Response(status_code=204)
