"""The context layer's §15 entry points (arch 15.1), with the exact signatures.

Real: `evaluate_transaction` (C6, `context.evaluate`), `pick_question` and `default_reading` (C7,
`context.questions`). Still S0 stubs, until C4 (`signatures_for_fact`), C9 (`on_fact_changed`),
C8 (`learn_from_annotation`) and C10 (`infer_hypotheses`): `[]`, a no-op result, `None`.

`db` is typed `Any` until bomboe's session exists. The DB reads go through bomboe's services
(arch 15.1 `services/`), looked up at call time because B3 isn't merged yet; tests replace them.
"""

import importlib
from datetime import date, timedelta
from typing import Any

from app import clock
from app.config import get_settings
from app.context import questions
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

# ── bomboe's services (B3), looked up at call time ───────────────────────────────────────────


def _service(name: str) -> Any:
    return importlib.import_module(f"app.services.{name}")


def _transaction(db: Any, user_id: int, tx_id: int) -> TxView:
    tx: TxView = _service("transactions").get(db, user_id, tx_id)
    return tx


def _transactions_of_day(db: Any, user_id: int, day: date) -> list[TxView]:
    txs: list[TxView] = _service("transactions").list_effective(db, user_id, day, day)
    return txs


def _context(db: Any, user_id: int, today: date) -> UserContext:
    """bomboe's B4 read model. NOTE: WB B4 declares it `async`; this shell is sync (§15), so the
    pipeline must hand over a sync loader or this shell becomes async (open point, C5-C7 report)."""
    ctx: UserContext = _service("context").load_user_context(db, user_id, today)
    return ctx


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


def evaluate_transaction(db: Any, user_id: int, tx_id: int) -> Evaluation:
    """C6: load the transaction and the context, then the pure `evaluate` (5.3.4). Pure read +
    compute: the pipeline saves it (`transactions.save_evaluation`)."""
    tx = _transaction(db, user_id, tx_id)
    return evaluate(_context(db, user_id, clock.today()), tx)


def pick_question(db: Any, user_id: int, today: date) -> QuestionCandidate | None:
    """C7: the one question to ask now among the `ask` / `ask_later` transactions of the last
    48 h (5.3.6), or None. The caller turns the others into ask_later / expired events."""
    ctx = _context(db, user_id, today)
    recent = [
        *_transactions_of_day(db, user_id, today - timedelta(days=2)),
        *_transactions_of_day(db, user_id, today - timedelta(days=1)),
        *_transactions_of_day(db, user_id, today),
    ]
    waiting = {tx.id: tx for tx in recent if tx.decision in (Decision.ASK, Decision.ASK_LATER)}
    candidates = [_candidate(ctx, tx) for tx in waiting.values()]
    return questions.pick_question(candidates, ctx, clock.now(), get_settings().SIM_MODE)


def signatures_for_fact(
    fact: LifeFact, llm_signatures: list[dict[str, Any]] | None
) -> list[Signature]:
    """Stub of C4: no signatures yet."""
    return []


def on_fact_changed(db: Any, user_id: int, fact_id: int) -> PropagationResult:
    """Stub of C9: a no-op (nothing re-evaluated, the scale unchanged)."""
    return PropagationResult(fact_id=fact_id)


def learn_from_annotation(db: Any, user_id: int, tx_id: int) -> RuleChange | None:
    """Stub of C8: never learns a rule."""
    return None


def infer_hypotheses(db: Any, user_id: int) -> list[LifeFactDraft]:
    """Stub of C10: no hypotheses."""
    return []
