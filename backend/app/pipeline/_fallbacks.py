"""Temporary stand-ins for teammates' functions (arch 15.1), used by `ports.py` only while the
real module doesn't exist. Behaviour = the S0 stub descriptions in Danutu.md / DGAdavid1.md.
Delete this file once `app/engine/service.py`, `app/context/service.py` and
`app/agent/proactive.py` are merged."""

import contextlib
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import local_date
from app.domain import models as dm
from app.domain.enums import AgentEventType, Category, Decision, Direction, Purpose
from app.domain.results import Evaluation, Forecast, PlanResult, PlanSummary, QuestionCandidate
from app.errors import DomainError
from app.services import accounts, agent_events, forecasts, goals, ledger, plans, transactions

ASK_ABOVE = Decimal("300")


async def evaluate_transaction(db: AsyncSession, user_id: int, tx_id: int) -> Evaluation:
    """S0 (David G.): `ask` with a provisional reading above 300 lei, else `auto`."""
    tx = await transactions.get(db, user_id, tx_id)
    ask = tx.direction == Direction.DEBIT and tx.amount > ASK_ABOVE
    return Evaluation(
        category=tx.category
        or (Category.INCOME if tx.direction == Direction.CREDIT else Category.OTHER),
        merchant_id=tx.merchant_id,
        merchant=tx.merchant,
        purpose=Purpose.UNKNOWN,
        effective_amount=tx.amount,
        life_fit=0,
        anomaly_score=0.8 if ask else 0,
        unexplained=0.72 if ask else 0,
        decision=Decision.ASK if ask else Decision.AUTO,
    )


async def apply_transaction(db: AsyncSession, user_id: int, tx_id: int) -> None:
    """S0 (danutu): balance moves by `amount`; that Bucharest day's spent by `effective_amount`."""
    tx = await transactions.get(db, user_id, tx_id)
    sign = Decimal("-1") if tx.direction == Direction.DEBIT else Decimal("1")
    with contextlib.suppress(DomainError):  # a user without an account row (fallback only)
        await accounts.adjust_balance(db, user_id, sign * tx.amount)
    if tx.direction == Direction.DEBIT:
        await ledger.add_spent(db, user_id, local_date(tx.occurred_at), tx.effective_amount)


async def recompute_plan(
    db: AsyncSession, user_id: int, reason: str, trigger_ref: dict[str, Any] | None = None
) -> PlanSummary | None:
    """S0 (danutu): a fixed plan; None without an active goal."""
    if await goals.get_active(db, user_id) is None:
        return None
    result = PlanResult(today_budget=Decimal("31.20"), feasible=True)
    return await plans.save(db, user_id, result, reason=reason, trigger_ref=trigger_ref)


async def forecast_goal(db: AsyncSession, user_id: int, plan_version: int) -> Forecast:
    """S0 (danutu): probability 0.78, saved."""
    goal = await goals.get_active(db, user_id)
    fc = Forecast(
        probability=0.78,
        p10=Decimal("8650"),
        p50=Decimal("10900"),
        p90=Decimal("12400"),
        plan_version=plan_version,
    )
    if goal is not None:
        await forecasts.save(db, user_id, fc, goal_id=goal.id, reason="new transactions")
    return await forecasts.latest(db, user_id) or fc


async def auto_save(db: AsyncSession, user_id: int, income_tx_id: int) -> dm.Transfer | None:
    """S0 (danutu): never a salary."""
    return None


async def pick_question(db: AsyncSession, user_id: int, today: date) -> QuestionCandidate | None:
    """S0 (David G.): the newest `ask` transaction of today, if today's question is free."""
    if await agent_events.question_asked_today(db, user_id, today):
        return None
    asked = {
        e.ref_transaction_id
        for e in await agent_events.pending_for(db, user_id)
        if e.type == AgentEventType.TRANSACTION_QUESTION
    }
    for tx in await transactions.list_effective(db, user_id, today, today):
        if tx.decision == Decision.ASK and tx.id not in asked:
            return QuestionCandidate(transaction_id=tx.id, priority=tx.unexplained or 0)
    return None


async def run_proactive(user_id: int, event_id: int) -> None:
    """S0 (David G.): would ask the question; does nothing here."""
