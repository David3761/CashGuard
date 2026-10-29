"""Domain objects → response shapes (shared by /state, /plan, /transactions, …)."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import schemas as s
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import AgentEventStatus, AgentEventType, Decision, LedgerStatus, TxStatus
from app.domain.results import PlanSummary
from app.pipeline import ports
from app.services import ledger


async def plan_out(db: AsyncSession, user_id: int, plan: PlanSummary, today: date) -> s.PlanOut:
    day = await ledger.get(db, user_id, today)
    return s.PlanOut(
        version=plan.version,
        feasible=plan.feasible,
        today_budget=plan.today_budget,
        spent_today=day.spent if day else Decimal("0"),
        today_status=day.status if day else LedgerStatus.OK,
        next_7_days=[s.DayOut(**d.model_dump()) for d in plan.next_7_days],
    )


async def streak_days(db: AsyncSession, user_id: int, today: date) -> int:
    """Consecutive days before today that closed ok or under budget."""
    days = {
        d.date: d
        for d in await ledger.between(
            db, user_id, today - timedelta(days=90), today - timedelta(days=1)
        )
    }
    streak, day = 0, today - timedelta(days=1)
    while day in days and days[day].status in (LedgerStatus.OK, LedgerStatus.UNDER):
        streak += 1
        day -= timedelta(days=1)
    return streak


async def awaiting_ids(db: AsyncSession, user_id: int) -> set[int]:
    rows = await db.scalars(
        select(m.AgentEvent.ref_transaction_id).where(
            m.AgentEvent.user_id == user_id,
            m.AgentEvent.type == AgentEventType.TRANSACTION_QUESTION,
            m.AgentEvent.status.in_([AgentEventStatus.PENDING, AgentEventStatus.ASKED]),
        )
    )
    return {r for r in rows if r is not None}


def transaction_out(tx: dm.TxView, language: str, awaiting: set[int]) -> s.TransactionOut:
    return s.TransactionOut(
        id=tx.id,
        occurred_at=tx.occurred_at,
        merchant=tx.merchant or tx.merchant_raw,
        category=tx.category,
        category_label=ports.label(tx.category, language),
        amount=tx.amount,
        effective_amount=tx.effective_amount,
        purpose=tx.purpose,
        purpose_label=ports.label(tx.purpose, language),
        explanation=tx.explanation,
        decision=tx.decision,
        annotation_source=tx.annotation_source,
        awaiting_answer=tx.decision == Decision.ASK and tx.id in awaiting,
        items=[i.model_dump(mode="json") for i in tx.items] if tx.items else None,
        receivable_id=tx.receivable_id,
        pot_id=tx.pot_id,
        status=tx.status or TxStatus.RESOLVED,
    )
