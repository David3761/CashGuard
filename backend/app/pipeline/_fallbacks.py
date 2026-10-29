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
from app.domain.enums import (
    AgentEventType,
    AnnotationSource,
    Beneficiary,
    Category,
    Decision,
    Direction,
    Language,
    Purpose,
)
from app.domain.models import LifeFact, LifeFactDraft, Signature, TxView
from app.domain.money import split_share
from app.domain.results import (
    AgentResult,
    Evaluation,
    Forecast,
    PlanResult,
    PlanSummary,
    PropagationResult,
    QuestionCandidate,
)
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


# ── more stand-ins (B6, B9, B10, B11, B12) ───────────────────────────────────────────────

PURPOSE_LABELS = {
    "ro": {
        "essential_living": "Necesar",
        "household_care": "Pentru casă și familie",
        "work_tool": "Echipament de lucru",
        "self_investment": "Investiție în tine",
        "identity_joy": "Ce te bucură",
        "social_connection": "Cu prietenii / colegii",
        "planned_event": "Plănuit",
        "on_behalf_of_others": "Pentru alții",
        "unplanned_discretionary": "Neplanificat",
        "emergency": "Urgență",
        "unknown": "În așteptare",
    },
    "en": {
        "essential_living": "Essentials",
        "household_care": "Home & family",
        "work_tool": "Work equipment",
        "self_investment": "Self-investment",
        "identity_joy": "Things you love",
        "social_connection": "Social",
        "planned_event": "Planned",
        "on_behalf_of_others": "For others",
        "unplanned_discretionary": "Unplanned",
        "emergency": "Emergency",
        "unknown": "Pending",
    },
}
CATEGORY_LABELS = {
    "ro": {
        "groceries": "Cumpărături",
        "restaurants": "Restaurante",
        "food_delivery": "Livrări mâncare",
        "transport": "Transport",
        "fuel": "Carburant",
        "electronics": "Electronice",
        "clothing": "Haine",
        "sport": "Sport",
        "health_pharmacy": "Sănătate",
        "kids": "Copii",
        "education": "Educație",
        "books": "Cărți",
        "entertainment": "Distracție",
        "subscriptions": "Abonamente",
        "travel": "Călătorii",
        "housing_rent": "Chirie",
        "utilities": "Utilități",
        "telecom": "Telefon & internet",
        "gifts": "Cadouri",
        "pets": "Animale",
        "household_goods": "Casă",
        "personal_care": "Îngrijire",
        "transfers": "Transferuri",
        "income": "Venit",
        "savings": "Economii",
        "other": "Altele",
    },
}


def label(value: str | None, lang: str) -> str | None:
    """C1 stand-in: RO/EN label of a purpose or category value (EN categories: Title case)."""
    if value is None:
        return None
    if value in PURPOSE_LABELS["ro"]:
        return PURPOSE_LABELS.get(lang, PURPOSE_LABELS["ro"])[value]
    if lang == "ro":
        return CATEGORY_LABELS["ro"].get(value, value)
    return value.replace("_", " ").capitalize()


def format_money(amount: Decimal | float | int, lang: str) -> str:
    """C1 stand-in: RO "10.000 lei" / "30,40 lei"; EN "10,000 lei" / "1,234.50 lei"."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"))
    whole = value == value.to_integral()
    text = f"{value:,.0f}" if whole else f"{value:,.2f}"
    if lang == "ro":
        text = text.replace(",", "§").replace(".", ",").replace("§", ".")
    return f"{text} lei"


async def run_agent(
    user_id: int, trigger: str, user_message: str | None, input_mode: str = "text"
) -> AgentResult:
    """S0 (David G.): echoes the message."""
    return AgentResult(text=f"Am primit: {user_message}")


def detect_language(text: str, current: Language) -> Language:
    """S0 (David G.): keeps the current language."""
    return current


FALLBACK_REPLY = {
    "ro": "Am o problemă acum, dar planul tău e în continuare la zi.",
    "en": "I'm having trouble right now, your plan is still up to date.",
}


def fallback_reply(language: str) -> str:
    """A5 stand-in: the arch §7 fallback text."""
    return FALLBACK_REPLY.get(language, FALLBACK_REPLY["ro"])


async def apply_annotation(
    db: AsyncSession,
    user_id: int,
    tx_id: int,
    purpose: Purpose,
    beneficiary: Beneficiary,
    own_amount: Decimal | None = None,
    people_count: int | None = None,
    others_will_repay: bool = False,
    debtor_label: str | None = None,
    source: AnnotationSource = AnnotationSource.USER_EDIT,
) -> TxView:
    """S0 (David G.'s shared annotate logic, A3): own_amount wins over people_count; the
    ledger moves by the effective-amount delta (danutu's on_annotation_changed)."""
    tx = await transactions.get(db, user_id, tx_id)
    effective = tx.effective_amount
    if own_amount is not None:
        effective = own_amount
    elif people_count is not None:
        effective, _ = split_share(tx.amount, people_count)
    new = await transactions.annotate(
        db,
        user_id,
        tx_id,
        purpose=purpose,
        beneficiary=beneficiary,
        effective_amount=effective,
        source=source,
    )
    if tx.direction == Direction.DEBIT and new.effective_amount != tx.effective_amount:
        await ledger.add_spent(
            db, user_id, local_date(tx.occurred_at), new.effective_amount - tx.effective_amount
        )
    return new


def default_reading(tx: TxView) -> tuple[Purpose, float]:
    """S0 (David G., C7): unanswered for 24 h → unplanned, confidence 0.3."""
    return Purpose.UNPLANNED_DISCRETIONARY, 0.3


def signatures_for_fact(
    fact: LifeFact, llm_signatures: list[dict[str, Any]] | None = None
) -> list[Signature]:
    """S0 (David G., C4): no library yet."""
    return []


async def on_fact_changed(db: AsyncSession, user_id: int, fact_id: int) -> PropagationResult:
    """S0 (David G., C9): just re-plans."""
    plan = await recompute_plan(
        db, user_id, reason="life fact changed", trigger_ref={"fact_id": fact_id}
    )
    return PropagationResult(fact_id=fact_id, plan_version=plan.version if plan else None)


async def infer_hypotheses(db: AsyncSession, user_id: int) -> list[LifeFactDraft]:
    """S0 (David G., C10): nothing inferred."""
    return []


async def recompute_baselines(db: AsyncSession, user_id: int) -> dict[str, Any]:
    """S0 (danutu, E6): keeps whatever is cached."""
    return {}
