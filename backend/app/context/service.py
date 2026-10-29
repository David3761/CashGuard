"""The context layer's §15 entry points (arch 15.1), with the exact signatures.

Real: `evaluate_transaction` (C6, `context.evaluate`), `pick_question` and `default_reading` (C7,
`context.questions`), `signatures_for_fact` (C4, `context.library`), `learn_from_annotation` (C8,
`context.rules`), `on_fact_changed` (C9, `context.propagate`) and `infer_hypotheses` (C10,
`context.inference`).

The shells that load data (`evaluate_transaction`, `pick_question`, `on_fact_changed`,
`learn_from_annotation`, `infer_hypotheses`) are `async`: bomboe's services and B4's
`load_user_context` run on SQLAlchemy's `AsyncSession`. The pure ones (`default_reading`,
`signatures_for_fact`) and the cores they call stay sync.

`db` is typed `Any` until bomboe's session exists. The DB reads go through bomboe's services
(arch 15.1 `services/`), looked up at call time because B3 isn't merged yet; tests replace them.
"""

import importlib
from datetime import date, timedelta
from typing import Any

from app import clock
from app.config import get_settings
from app.context import inference, library, questions, rules
from app.context.evaluate import evaluate, goal_impact
from app.domain.enums import Decision
from app.domain.models import LifeFact, LifeFactDraft, PatternRule, Signature, TxView
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


async def _transaction(db: Any, user_id: int, tx_id: int) -> TxView:
    tx: TxView = await _service("transactions").get(db, user_id, tx_id)
    return tx


async def _transactions_of_day(db: Any, user_id: int, day: date) -> list[TxView]:
    txs: list[TxView] = await _service("transactions").list_effective(db, user_id, day, day)
    return txs


async def _context(db: Any, user_id: int, today: date) -> UserContext:
    """bomboe's B4 read model (`async`, WB B4; so are the shells that call it)."""
    ctx: UserContext = await _service("context_loader").load_user_context(db, user_id, today)
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


async def evaluate_transaction(db: Any, user_id: int, tx_id: int) -> Evaluation:
    """C6: load the transaction and the context, then the pure `evaluate` (5.3.4). Pure read +
    compute: the pipeline saves it (`transactions.save_evaluation`)."""
    tx = await _transaction(db, user_id, tx_id)
    return evaluate(await _context(db, user_id, clock.today()), tx)


async def pick_question(db: Any, user_id: int, today: date) -> QuestionCandidate | None:
    """C7: the one question to ask now among the `ask` / `ask_later` transactions of the last
    48 h (5.3.6), or None. The caller turns the others into ask_later / expired events."""
    ctx = await _context(db, user_id, today)
    recent = [
        *await _transactions_of_day(db, user_id, today - timedelta(days=2)),
        *await _transactions_of_day(db, user_id, today - timedelta(days=1)),
        *await _transactions_of_day(db, user_id, today),
    ]
    waiting = {tx.id: tx for tx in recent if tx.decision in (Decision.ASK, Decision.ASK_LATER)}
    candidates = [_candidate(ctx, tx) for tx in waiting.values()]
    return questions.pick_question(candidates, ctx, clock.now(), get_settings().SIM_MODE)


def signatures_for_fact(
    fact: LifeFact, llm_signatures: list[dict[str, Any]] | None
) -> list[Signature]:
    """C4: the library's signatures for `fact`, then Claude's valid ones (5.3.3)."""
    return library.signatures_for_fact(fact, llm_signatures)


async def on_fact_changed(db: Any, user_id: int, fact_id: int) -> PropagationResult:
    """C9 (5.3.9): signatures → baselines → the last 30 days re-read → plan + forecast."""
    from app.context import propagate  # it uses this module's loaders

    return await propagate.on_fact_changed(db, user_id, fact_id)


async def save_rule_change(
    db: Any, user_id: int, old: PatternRule | None, change: RuleChange
) -> RuleChange:
    """Store what C8 decided through bomboe's `pattern_rules`: a new rule → `create`; else the
    difference from `old` → `record_hit` / `record_miss` / `set_confidence` / `deactivate`.
    Returns the change carrying the stored rule. Also used for `rules.decay`'s changes."""
    store = _service("pattern_rules")
    new = change.rule
    if old is None or old.id is None:
        return change.model_copy(update={"rule": await store.create(db, user_id, new)})
    saved = old
    if new.hits > old.hits:
        saved = await store.record_hit(db, user_id, old.id)
    if new.misses > old.misses:
        saved = await store.record_miss(db, user_id, old.id)
    if new.confidence != old.confidence:
        saved = await store.set_confidence(db, user_id, old.id, new.confidence)
    if old.active and not new.active:
        saved = await store.deactivate(db, user_id, old.id)
    return change.model_copy(update={"rule": saved})


async def learn_from_annotation(db: Any, user_id: int, tx_id: int) -> RuleChange | None:
    """C8 (5.3.7): what the user's explanation of `tx_id` teaches, stored; None when nothing."""
    tx = await _transaction(db, user_id, tx_id)
    ctx = await _context(db, user_id, clock.today())
    change = rules.learn(tx, ctx.transactions, ctx.rules)
    if change is None:
        return None
    old = next((r for r in ctx.rules if r.id is not None and r.id == change.rule.id), None)
    return await save_rule_change(db, user_id, old, change)


async def _rejected_facts(db: Any, user_id: int) -> list[LifeFact]:
    """The user's rejected facts (F16 "never again"). bomboe's B3 `life_facts` lists active and
    hypotheses only; until it has `list_rejected`, nothing is known to be rejected (handoff)."""
    list_rejected = getattr(_service("life_facts"), "list_rejected", None)
    if list_rejected is None:
        return []
    rejected: list[LifeFact] = list(await list_rejected(db, user_id))
    return rejected


async def infer_hypotheses(db: Any, user_id: int) -> list[LifeFactDraft]:
    """C10: at most one new hypothesis from the user's transactions (5.3.8), never a sensitive
    type, never one the user already confirmed, has open or rejected. The caller saves it
    (`life_facts.create`) and pushes WS `fact.hypothesis` with `inference.question_for`."""
    today = clock.today()
    ctx = await _context(db, user_id, today)
    return inference.infer_hypotheses(ctx, today, await _rejected_facts(db, user_id))
