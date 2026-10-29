"""C9: propagation on a fact change ("every life change re-plans the roadmap"; arch 5.3.9).

Pure core:
- `reevaluate(ctx, transactions, today)`: the last 30 days read again with the new life (C6's
  `evaluate`). **Only** readings the system made itself are re-read: `annotation_source` in
  {auto, fact, default}. The user's own answer or edit is never overridden (5.3.2), and neither is
  a rule or a pot reading. Only the transactions whose reading changes are returned (purpose,
  beneficiary, effective amount, decision, source, explanation, matched fact / rule, pot), so a
  second run returns nothing. A past transaction never turns into a new question: a re-read that
  would ask gets the default reading instead (a question already waiting stays as it is).
- `scale_windows(before, after, start, end)`: the days where the household scale differs with
  the fact as it is now vs without it ("mama stă la noi în iulie" → 2.1 → 2.6 in July only).

Shells (DB through bomboe's services and danutu's engine, looked up at call time):
- `reevaluate_after_fact(db, user_id, fact_id)`: the fact's signatures (the library's + the
  Claude ones it already has; none when it's no longer confirmed) → `recompute_baselines` →
  re-evaluate → `save_evaluation` + `on_annotation_changed` for each change. The tool handlers
  call this one (C4 already saved Claude's signatures, and the executor recomputes the plan, D18).
- `on_fact_changed(db, user_id, fact_id)` (§15): the same, then `recompute_plan(reason="fact: …")`
  and `forecast_goal`. For the REST profile edits (B6b) and every caller outside a tool.
"""

import importlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Final

from app import clock
from app.clock import APP_TZ
from app.context import library, questions
from app.context.evaluate import evaluate
from app.domain.enums import AnnotationSource, Decision, FactStatus, SignatureOrigin
from app.domain.models import LifeFact, Signature, TxView
from app.domain.results import Evaluation, PropagationResult
from app.domain.user_context import UserContext
from app.engine.baselines import household_scale

WINDOW_DAYS: Final = 30
SCALE_HORIZON_DAYS: Final = 365
REEVALUATED_SOURCES: Final = frozenset(
    {AnnotationSource.AUTO, AnnotationSource.FACT, AnnotationSource.DEFAULT}
)
WAITING: Final = (Decision.ASK, Decision.ASK_LATER)
_READING_FIELDS: Final = (
    "category", "purpose", "beneficiary", "effective_amount", "annotation_source", "decision",
    "explanation", "matched_fact_id", "matched_rule_id", "pot_id",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class AnnotationChange:
    """One transaction whose reading changes: what it was and the new evaluation to store."""

    transaction_id: int
    old: TxView
    evaluation: Evaluation


@dataclass(frozen=True, slots=True)
class ScaleWindow:
    """Consecutive days (both inclusive) where the fact moves the household scale."""

    start: date
    end: date
    before: Decimal
    after: Decimal


# ── pure core ────────────────────────────────────────────────────────────────────────────────


def reevaluable(tx: TxView, today: date) -> bool:
    """A reading the system made (auto / fact / default) in the last 30 days (inclusive)."""
    day = tx.occurred_at.astimezone(APP_TZ).date()
    recent = today - timedelta(days=WINDOW_DAYS) <= day <= today
    return recent and tx.annotation_source in REEVALUATED_SOURCES


def _differs(tx: TxView, evaluation: Evaluation) -> bool:
    return any(getattr(tx, name) != getattr(evaluation, name) for name in _READING_FIELDS)


def new_reading(ctx: UserContext, tx: TxView) -> Evaluation:
    """C6 with the new life; a past transaction is never turned into a new question."""
    evaluation = evaluate(ctx, tx)
    if evaluation.decision is not Decision.ASK:
        return evaluation
    if tx.decision in WAITING:  # the question is already waiting: keep its state
        return evaluation.model_copy(update={"decision": tx.decision})
    return questions.default_reading(tx)


def reevaluate(
    ctx: UserContext, transactions: Iterable[TxView], today: date
) -> tuple[AnnotationChange, ...]:
    """The re-readable transactions of the last 30 days whose reading changes, oldest first."""
    changes = []
    for tx in sorted(transactions, key=lambda t: (t.occurred_at, t.id)):
        if not reevaluable(tx, today):
            continue
        evaluation = new_reading(ctx, tx)
        if _differs(tx, evaluation):
            changes.append(AnnotationChange(tx.id, tx, evaluation))
    return tuple(changes)


def scale_windows(
    before: Sequence[LifeFact], after: Sequence[LifeFact], start: date, end: date
) -> tuple[ScaleWindow, ...]:
    """The runs of days in [start, end] where the household scale differs (E6's scale)."""
    windows: list[ScaleWindow] = []
    day = start
    while day <= end:
        old, new = household_scale(before, day), household_scale(after, day)
        if old != new:
            last = windows[-1] if windows else None
            yesterday = day - timedelta(days=1)
            if last and last.end == yesterday and (last.before, last.after) == (old, new):
                windows[-1] = ScaleWindow(last.start, day, old, new)
            else:
                windows.append(ScaleWindow(day, day, old, new))
        day += timedelta(days=1)
    return tuple(windows)


def fact_scale_windows(
    facts: Sequence[LifeFact], fact: LifeFact, today: date
) -> tuple[ScaleWindow, ...]:
    """The scale with `fact` as it is now vs without it, from 30 days ago to a year ahead."""
    others = [f for f in facts if f.id != fact.id]
    return scale_windows(
        others,
        [*others, fact],
        today - timedelta(days=WINDOW_DAYS),
        today + timedelta(days=SCALE_HORIZON_DAYS),
    )


def fact_signatures(fact: LifeFact, stored: Iterable[Signature]) -> list[Signature]:
    """The fact's signatures after a change: the library's, plus the Claude ones it already had
    on an effect + category the library doesn't cover (5.3.3); none unless confirmed."""
    if fact.status is not FactStatus.CONFIRMED:
        return []
    fresh = library.library_signatures(fact)
    taken = {(s.effect, s.category) for s in fresh}
    claude = [
        s.replace(id=None)
        for s in stored
        if s.origin is SignatureOrigin.LLM and (s.effect, s.category) not in taken
    ]
    return [*fresh, *claude]


def plan_reason(fact: LifeFact) -> str:
    return f"fact: {fact.type} {fact.text}"[:300]


# ── shells ───────────────────────────────────────────────────────────────────────────────────


def _service(name: str) -> Any:
    return importlib.import_module(f"app.services.{name}")


def _engine(name: str) -> Any:
    return getattr(importlib.import_module("app.engine.service"), name)


def _context(db: Any, user_id: int, today: date) -> UserContext:
    from app.context import service  # the one B4 loader the other shells use

    return service._context(db, user_id, today)


def reevaluate_after_fact(db: Any, user_id: int, fact_id: int) -> PropagationResult:
    """Signatures → baselines → the last 30 days re-read and saved (+ ledger deltas). No plan:
    the tool executor recomputes it once after the tool (D18)."""
    today = clock.today()
    fact: LifeFact = _service("life_facts").get(db, user_id, fact_id)
    signatures = _service("signatures")
    stored = signatures.list_for_fact(db, user_id, fact_id)
    signatures.replace_for_fact(db, user_id, fact_id, fact_signatures(fact, stored))
    _engine("recompute_baselines")(db, user_id)
    ctx = _context(db, user_id, today)
    transactions = _service("transactions")
    recent = transactions.list_effective(db, user_id, today - timedelta(days=WINDOW_DAYS), today)
    changes = reevaluate(ctx, recent, today)
    for change in changes:
        saved = transactions.save_evaluation(db, user_id, change.transaction_id, change.evaluation)
        _engine("on_annotation_changed")(db, user_id, change.transaction_id, change.old, saved)
    return PropagationResult(
        fact_id=fact_id,
        household_scale=household_scale(ctx.facts, today),
        changed_transaction_ids=tuple(c.transaction_id for c in changes),
    )


def on_fact_changed(db: Any, user_id: int, fact_id: int) -> PropagationResult:
    """§15 (5.3.9): `reevaluate_after_fact`, then `recompute_plan(reason="fact: …")` and
    `forecast_goal` on the new plan version."""
    result = reevaluate_after_fact(db, user_id, fact_id)
    fact: LifeFact = _service("life_facts").get(db, user_id, fact_id)
    plan = _engine("recompute_plan")(db, user_id, plan_reason(fact), {"fact_id": fact_id})
    forecast = _engine("forecast_goal")(db, user_id, plan.version)
    return result.model_copy(update={"plan": plan, "forecast": forecast})
