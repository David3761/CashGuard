"""Receivables (arch 9.2, B6b step 1). request-payment is the user's tap (D31); a mock."""

from fastapi import APIRouter
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.api import schemas as s
from app.api.deps import CurrentUser, Db
from app.domain import models as dm
from app.domain.enums import ReceivableStatus
from app.pipeline import ports
from app.services import receivables
from app.services.notify import notify
from app.ws import push_after_commit

router = APIRouter(tags=["receivables"])


def out(r: dm.Receivable) -> s.ReceivableOut:
    return s.ReceivableOut(**r.model_dump())


async def _replan(db: AsyncSession, user_id: int, receivable_id: int, why: str) -> None:
    plan = await ports.recompute_plan(
        db, user_id, reason=why, trigger_ref={"receivable_id": receivable_id}
    )
    if plan is not None:
        push_after_commit(db, user_id, events.plan_updated(plan))
        forecast = await ports.forecast_goal(db, user_id, plan.version)
        push_after_commit(db, user_id, events.forecast_updated(forecast))


@router.get("/receivables")
async def list_receivables(
    user: CurrentUser, db: Db, status: ReceivableStatus | None = None
) -> s.ReceivablesOut:
    return s.ReceivablesOut(
        receivables=[out(r) for r in await receivables.list_all(db, user.id, status)]
    )


@router.post("/receivables/{receivable_id}/request-payment")
async def request_payment(receivable_id: int, user: CurrentUser, db: Db) -> s.ReceivableOut:
    r = await receivables.update_status(db, user.id, receivable_id, ReceivableStatus.REQUESTED)
    others = max((r.people_count or 2) - 1, 1)
    each = r.amount_each if r.amount_each is not None else r.amount
    await notify(db, user.id, "payment_request_sent", {"count": others, "each": each})
    push_after_commit(db, user.id, events.receivable_updated(r))
    await db.commit()
    return out(r)


@router.post("/receivables/{receivable_id}/mark-paid")
async def mark_paid(receivable_id: int, user: CurrentUser, db: Db) -> s.ReceivableOut:
    r = await receivables.update_status(db, user.id, receivable_id, ReceivableStatus.PAID)
    push_after_commit(db, user.id, events.receivable_updated(r))
    await _replan(db, user.id, r.id, "receivable paid")
    await db.commit()
    return out(r)


@router.post("/receivables/{receivable_id}/cancel")
async def cancel(receivable_id: int, user: CurrentUser, db: Db) -> s.ReceivableOut:
    r = await receivables.cancel(db, user.id, receivable_id)
    push_after_commit(db, user.id, events.receivable_updated(r))
    await _replan(db, user.id, r.id, "receivable cancelled")
    await db.commit()
    return out(r)
