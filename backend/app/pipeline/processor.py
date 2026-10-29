"""`process_user`: the processing pipeline (arch F3, B8).

One transaction per user run, serialised by `pg_advisory_xact_lock(user_id)`; each queued
transaction in its own SAVEPOINT (evaluate → save → apply → resolved); then auto-save, re-plan,
forecast, today's question, and (outside chat) a proactive run after the commit.
"""

import logging
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock, events
from app.db import models as m
from app.db.session import unit_of_work
from app.domain.enums import AgentEventType, Direction, TransactionStatus
from app.logging import redact
from app.pipeline import ports
from app.services import agent_events, transactions, transfers
from app.ws import push_after_commit

log = logging.getLogger(__name__)
STALE_AFTER = timedelta(minutes=5)


@dataclass(frozen=True)
class ProcessResult:
    resolved: int = 0
    failed: int = 0
    retried: int = 0
    question_event_id: int | None = None


async def _claim(db: AsyncSession, user_id: int) -> list[int]:
    queued = (
        select(m.Transaction.id)
        .where(
            m.Transaction.user_id == user_id, m.Transaction.status == TransactionStatus.UNRESOLVED
        )
        .order_by(m.Transaction.occurred_at, m.Transaction.id)
        .with_for_update(skip_locked=True)
    )
    claimed = await db.execute(
        update(m.Transaction)
        .where(m.Transaction.id.in_(queued.scalar_subquery()))
        .values(status=TransactionStatus.PROCESSING, locked_at=clock.now())
        .returning(m.Transaction.id)
        .execution_options(synchronize_session=False)
    )
    return sorted(claimed.scalars())


async def _process_one(db: AsyncSession, user_id: int, tx_id: int) -> bool:
    try:
        async with db.begin_nested():
            evaluation = await ports.evaluate_transaction(db, user_id, tx_id)
            await transactions.save_evaluation(db, user_id, tx_id, evaluation)
            await ports.apply_transaction(db, user_id, tx_id)
            tx = await transactions.mark_resolved(db, user_id, tx_id)
    except Exception as exc:
        log.warning("transaction %s failed: %s", tx_id, exc)
        await transactions.bump_attempts(db, user_id, tx_id, redact(str(exc))[:500])
        return False
    push_after_commit(db, user_id, events.transaction_resolved(tx))
    push_after_commit(db, user_id, events.transaction_annotated(tx))
    return True


async def process_user(user_id: int, trigger: str) -> ProcessResult:
    """Process every unresolved transaction of the user (trigger: sim | cron | chat)."""
    async with unit_of_work() as db:
        await db.execute(text("SELECT pg_advisory_xact_lock(:u)"), {"u": user_id})
        ids = await _claim(db, user_id)
        if not ids:
            return ProcessResult()
        resolved = [tx_id for tx_id in ids if await _process_one(db, user_id, tx_id)]
        for tx_id in resolved:
            tx = await transactions.get(db, user_id, tx_id)
            if (
                tx.direction == Direction.CREDIT
                and await transfers.for_income(db, user_id, tx_id) is None
            ):
                await ports.auto_save(db, user_id, tx_id)
        question_id = None
        if resolved:
            plan = await ports.recompute_plan(db, user_id, reason="new transactions")
            if plan is not None:
                push_after_commit(db, user_id, events.plan_updated(plan))
                forecast = await ports.forecast_goal(db, user_id, plan.version)
                push_after_commit(db, user_id, events.forecast_updated(forecast))
            today = clock.today()
            candidate = await ports.pick_question(db, user_id, today)
            if candidate is not None:
                question = await agent_events.create(
                    db,
                    user_id,
                    type=AgentEventType.TRANSACTION_QUESTION,
                    event_date=today,
                    payload=candidate.hint.model_dump(mode="json") if candidate.hint else {},
                    ref_transaction_id=candidate.transaction_id,
                )
                question_id = question.id
        pending = await agent_events.pending_for(db, user_id)
        rows = await db.scalars(select(m.Transaction.status).where(m.Transaction.id.in_(ids)))
        failed = sum(1 for s in rows if s == TransactionStatus.FAILED)
    if pending and trigger != "chat":
        event_id = question_id or pending[0].id
        try:
            await ports.run_proactive(user_id, event_id)
        except Exception:
            log.exception("proactive run for event %s failed", event_id)
    return ProcessResult(
        resolved=len(resolved),
        failed=failed,
        retried=len(ids) - len(resolved) - failed,
        question_event_id=question_id,
    )


async def users_with_work() -> list[int]:
    async with unit_of_work() as db:
        rows = await db.scalars(
            select(m.Transaction.user_id)
            .where(m.Transaction.status == TransactionStatus.UNRESOLVED)
            .distinct()
        )
        return sorted(rows)


async def recover_stale() -> int:
    """`processing` rows locked more than 5 minutes ago go back to `unresolved` (a crash)."""
    async with unit_of_work() as db:
        result = await db.execute(
            update(m.Transaction)
            .where(
                m.Transaction.status == TransactionStatus.PROCESSING,
                m.Transaction.locked_at < clock.now() - STALE_AFTER,
            )
            .values(status=TransactionStatus.UNRESOLVED, locked_at=None)
            .returning(m.Transaction.id)
            .execution_options(synchronize_session=False)
        )
        return len(list(result.scalars()))
