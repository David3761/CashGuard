"""The context layer's §15 entry points (arch 15.1), with the exact signatures.

Real: `evaluate_transaction` (C6, `context.evaluate`), `pick_question` and `default_reading` (C7,
`context.questions`), `signatures_for_fact` (C4, `context.library`). Still S0 stubs, until C9
(`on_fact_changed`), C8 (`learn_from_annotation`) and C10 (`infer_hypotheses`): `[]`, a no-op
result, `None`.

The shells are async (HANDOFFS H-12, settled at the integration): bomboe's B4 loader and B3
services are async. The DB reads go through his services; the pure cores stay sync.
"""

from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.config import get_settings
from app.context import library, questions
from app.context.evaluate import evaluate, goal_impact
from app.domain.enums import Decision
from app.domain.models import LifeFact, LifeFactDraft, Signature, TxView
from app.domain.results import (
    Evaluation,
    PropagationResult,
    QuestionCandidate,
    QuestionHint,
    RuleChange,
)
from app.domain.user_context import UserContext
from app.services import transactions as transactions_service
from app.services.context_loader import load_user_context


def _candidate(ctx: UserContext, tx: TxView) -> QuestionCandidate:
    hint = evaluate(ctx, tx).question_hint or QuestionHint(reason="large_amount")
    return QuestionCandidate(
        transaction_id=tx.id,
        occurred_at=tx.occurred_at,
        unexplained=tx.unexplained if tx.unexplained is not None else 0.0,
        goal_impact=goal_impact(ctx, tx.amount),
        question_hint=hint,
    )


# ── the §15 functions ────────────────────────────────────────────────────────────────────────


def default_reading(tx: TxView) -> Evaluation:
    """C7: the reading used when nobody answered (5.3.6 #7): the whole amount,
    `unplanned_discretionary`, confidence 0.3, source `default`."""
    return questions.default_reading(tx)


async def evaluate_transaction(db: AsyncSession, user_id: int, tx_id: int) -> Evaluation:
    """C6: load the transaction and the context, then the pure `evaluate` (5.3.4). Pure read +
    compute: the pipeline saves it (`transactions.save_evaluation`)."""
    tx = await transactions_service.get(db, user_id, tx_id)
    return evaluate(await load_user_context(db, user_id, clock.today()), tx)


async def pick_question(db: AsyncSession, user_id: int, today: date) -> QuestionCandidate | None:
    """C7: the one question to ask now among the `ask` / `ask_later` transactions of the last
    48 h (5.3.6), or None. The caller turns the others into ask_later / expired events."""
    ctx = await load_user_context(db, user_id, today)
    recent = await transactions_service.list_effective(
        db, user_id, today - timedelta(days=2), today
    )
    waiting = {tx.id: tx for tx in recent if tx.decision in (Decision.ASK, Decision.ASK_LATER)}
    candidates = [_candidate(ctx, tx) for tx in waiting.values()]
    return questions.pick_question(candidates, ctx, clock.now(), get_settings().SIM_MODE)


def signatures_for_fact(
    fact: LifeFact, llm_signatures: list[dict[str, Any]] | None
) -> list[Signature]:
    """C4: the library's signatures for `fact`, then Claude's valid ones (5.3.3)."""
    return library.signatures_for_fact(fact, llm_signatures)


async def on_fact_changed(db: AsyncSession, user_id: int, fact_id: int) -> PropagationResult:
    """Stub of C9: a no-op (nothing re-evaluated, the scale unchanged)."""
    return PropagationResult(fact_id=fact_id)


async def learn_from_annotation(db: AsyncSession, user_id: int, tx_id: int) -> RuleChange | None:
    """Stub of C8: never learns a rule."""
    return None


async def infer_hypotheses(db: AsyncSession, user_id: int) -> list[LifeFactDraft]:
    """Stub of C10: no hypotheses."""
    return []
