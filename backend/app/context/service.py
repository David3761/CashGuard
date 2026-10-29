"""The context layer's §15 entry points (arch 15.1): S0 stubs with the exact signatures.

The real bodies come from C6 (`evaluate_transaction`), C7 (`pick_question`, `default_reading`), C4
(`signatures_for_fact`), C9 (`on_fact_changed`), C8 (`learn_from_annotation`) and C10
(`infer_hypotheses`). Until then the stubs give callers (bomboe's pipeline B8, A3's handlers) the
documented shapes:
- `evaluate_transaction`: `ask` with a provisional reading when `amount > 300`, else `auto`;
- `pick_question`: the first `ask` transaction of the day, if no question was asked today;
- `default_reading`: `unplanned_discretionary`, confidence 0.3, source `default` (5.3.6);
- the others: `[]`, a no-op result, `None`.

`db` is typed `Any` until bomboe's session exists. The DB reads go through bomboe's services
(arch 15.1 `services/`), looked up at call time because B3 isn't merged yet; tests replace them.
"""

import importlib
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final, Literal

from app.domain.enums import AnnotationSource, Beneficiary, Category, Decision, FactType, Purpose
from app.domain.models import DomainModel, TxView
from app.domain.money import Money

ASK_ABOVE: Final = Decimal("300")
"""The stub's whole policy: a transaction above 300 lei is asked about (DGAdavid1 S0)."""
DEFAULT_CONFIDENCE: Final = 0.3
"""The confidence of the default reading (5.3.6, C7 step 2)."""


# ── TODO(F2): placeholders with F2's planned names (F2.md steps 4, 5, 7). Replace each with the ──
# ── import from app.domain (models / results) when F2 lands; the fields here are a subset. ──────


class QuestionHint(DomainModel):  # TODO(F2): app.domain.results.QuestionHint
    reason: str
    ask_what_item: bool = False


class Evaluation(DomainModel):  # TODO(F2): app.domain.results.Evaluation
    category: Category
    merchant_id: str | None = None
    merchant: str | None = None
    purpose: Purpose
    beneficiary: Beneficiary
    effective_amount: Money
    annotation_source: AnnotationSource
    confidence: float
    life_fit: float = 0.0
    anomaly_score: float = 0.0
    unexplained: float = 0.0
    decision: Decision
    explanation: str | None = None
    matched_fact_id: int | None = None
    matched_rule_id: int | None = None
    pot_id: int | None = None
    goal_impact: float = 0.0
    question_hint: QuestionHint | None = None


class QuestionCandidate(DomainModel):  # TODO(F2): app.domain.results.QuestionCandidate
    transaction_id: int
    occurred_at: datetime
    unexplained: float
    goal_impact: float
    question_hint: QuestionHint


class LifeFactDraft(DomainModel):  # TODO(F2): app.domain.models.LifeFactDraft
    type: FactType
    text: str


class LifeFact(LifeFactDraft):  # TODO(F2): app.domain.models.LifeFact
    id: int


class Signature(DomainModel):  # TODO(F2): app.domain.models.Signature
    purpose: Purpose
    category: Category | None = None


class RuleChange(DomainModel):  # TODO(F2): app.domain.results.RuleChange (+ rule: PatternRule)
    action: Literal["created", "updated", "deactivated"]
    previous_confidence: float | None = None


class PropagationResult(DomainModel):  # TODO(F2): app.domain.results.PropagationResult
    fact_id: int
    household_scale: Decimal | None = None
    changed_transaction_ids: tuple[int, ...] = ()


# ── bomboe's services (B3), looked up at call time ───────────────────────────────────────────


def _service(name: str) -> Any:
    return importlib.import_module(f"app.services.{name}")


def _transaction(db: Any, user_id: int, tx_id: int) -> TxView:
    tx: TxView = _service("transactions").get(db, user_id, tx_id)
    return tx


def _transactions_of_day(db: Any, user_id: int, day: date) -> list[TxView]:
    txs: list[TxView] = _service("transactions").list_effective(db, user_id, day, day)
    return txs


def _question_asked_today(db: Any, user_id: int, today: date) -> bool:
    return bool(_service("agent_events").question_asked_today(db, user_id, today))


# ── the §15 functions ────────────────────────────────────────────────────────────────────────


def default_reading(tx: TxView) -> Evaluation:
    """The reading used when nobody answered (5.3.6): the whole amount, `unplanned_discretionary`,
    confidence 0.3, source `default`. Also the stub's provisional reading for a question."""
    return Evaluation(
        category=tx.category or Category.OTHER,
        merchant_id=tx.merchant_id,
        merchant=tx.merchant,
        purpose=Purpose.UNPLANNED_DISCRETIONARY,
        beneficiary=Beneficiary.SELF,
        effective_amount=tx.amount,
        annotation_source=AnnotationSource.DEFAULT,
        confidence=DEFAULT_CONFIDENCE,
        decision=Decision.AUTO,
    )


def evaluate_transaction(db: Any, user_id: int, tx_id: int) -> Evaluation:
    """Stub of C6: `ask` (with the default reading as the provisional one) above 300 lei, else
    `auto`. Pure read + compute: the pipeline saves it (`transactions.save_evaluation`)."""
    tx = _transaction(db, user_id, tx_id)
    reading = default_reading(tx)
    if tx.amount > ASK_ABOVE:
        return reading.replace(
            decision=Decision.ASK,
            unexplained=1.0,
            goal_impact=1.0,
            question_hint=QuestionHint(reason="stub_large_amount", ask_what_item=not tx.items),
        )
    return reading.replace(annotation_source=AnnotationSource.AUTO)


def pick_question(db: Any, user_id: int, today: date) -> QuestionCandidate | None:
    """Stub of C7: the first `ask` transaction of `today`, or None if a question was already
    asked today (the D25 budget of one question a day)."""
    if _question_asked_today(db, user_id, today):
        return None
    for tx in _transactions_of_day(db, user_id, today):
        if tx.decision == Decision.ASK:
            return QuestionCandidate(
                transaction_id=tx.id,
                occurred_at=tx.occurred_at,
                unexplained=tx.unexplained if tx.unexplained is not None else 1.0,
                goal_impact=1.0,
                question_hint=QuestionHint(reason="stub_large_amount", ask_what_item=not tx.items),
            )
    return None


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
