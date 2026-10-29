"""GET/PATCH /transactions (arch 9.2); PATCH = the user fixes a reading from the feed."""

from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Query

from app import events
from app.api import schemas as s
from app.api.deps import CurrentUser, Db
from app.api.views import awaiting_ids, transaction_out
from app.db import models as m
from app.domain.enums import AnnotationSource, Beneficiary, Purpose, TransactionStatus
from app.pipeline import ports
from app.services import transactions
from app.services._common import as_enum, invalid
from app.ws import push_after_commit

router = APIRouter(tags=["transactions"])


@router.get("/transactions")
async def list_transactions(
    user: CurrentUser,
    db: Db,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
    status: TransactionStatus | None = None,
) -> s.TransactionsOut:
    rows = await transactions.list_all(db, user.id, since=from_, until=to, status=status)
    awaiting = await awaiting_ids(db, user.id)
    return s.TransactionsOut(
        transactions=[transaction_out(t, user.language, awaiting) for t in rows]
    )


@router.get("/transactions/{tx_id}")
async def get_transaction(tx_id: int, user: CurrentUser, db: Db) -> s.TransactionDetail:
    tx = await transactions.get(db, user.id, tx_id)
    base = transaction_out(tx, user.language, await awaiting_ids(db, user.id))
    fact = await db.get(m.LifeFact, tx.matched_fact_id) if tx.matched_fact_id else None
    rule = await db.get(m.PatternRule, tx.matched_rule_id) if tx.matched_rule_id else None
    return s.TransactionDetail(
        **base.model_dump(),
        scores=s.Scores(
            life_fit=tx.life_fit, anomaly_score=tx.anomaly_score, unexplained=tx.unexplained
        ),
        matched_fact=s.Ref(id=fact.id, text=fact.text) if fact else None,
        matched_rule=s.Ref(id=rule.id, text=rule.outcome.get("label")) if rule else None,
    )


@router.patch("/transactions/{tx_id}")
async def patch_transaction(
    tx_id: int, body: s.TransactionPatch, user: CurrentUser, db: Db
) -> s.TransactionOut:
    tx = await transactions.get(db, user.id, tx_id)
    if body.own_amount is not None and not Decimal("0") <= body.own_amount <= tx.amount:
        raise invalid("invalid_own_amount", f"Your share must be between 0 and {tx.amount}.")
    if body.people_count is not None and body.people_count < 1:
        raise invalid("invalid_people_count", "people_count is at least 1.")
    shared = (body.own_amount is not None and body.own_amount < tx.amount) or (
        body.people_count or 1
    ) > 1
    purpose = (
        as_enum(Purpose, body.purpose, "invalid_purpose")
        if body.purpose
        else Purpose.ON_BEHALF_OF_OTHERS
        if shared
        else tx.purpose or Purpose.UNKNOWN
    )
    new = await ports.apply_annotation(
        db,
        user.id,
        tx_id,
        purpose,
        Beneficiary.SHARED if shared else Beneficiary.SELF,
        own_amount=body.own_amount,
        people_count=body.people_count,
        source=AnnotationSource.USER_EDIT,
    )
    plan = await ports.recompute_plan(
        db, user.id, reason="user edit", trigger_ref={"transaction_id": tx_id}
    )
    push_after_commit(
        db, user.id, events.transaction_annotated(new, ports.label(new.purpose, user.language))
    )
    if plan is not None:
        push_after_commit(db, user.id, events.plan_updated(plan))
        forecast = await ports.forecast_goal(db, user.id, plan.version)
        push_after_commit(db, user.id, events.forecast_updated(forecast))
    await db.commit()
    return transaction_out(new, user.language, await awaiting_ids(db, user.id))
