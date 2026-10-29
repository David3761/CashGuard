"""S0: the context layer's §15 stubs are importable and return the documented types."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.context import service
from app.domain.enums import AnnotationSource, Category, Decision, Direction, FactType, Purpose
from app.domain.models import Item, TxView
from app.domain.results import Evaluation, PropagationResult, QuestionCandidate
from tests.builders import fact

TODAY = date(2026, 6, 15)


def _tx(
    amount: str, *, tx_id: int = 1, decision: Decision | None = None, items: bool = True
) -> TxView:
    return TxView(
        id=tx_id,
        occurred_at=datetime(2026, 6, 15, 10, 5, tzinfo=UTC),
        merchant_raw="MEGA IMAGE 0451 BUCURESTI",
        merchant="Mega Image",
        merchant_id="mega_image",
        category=Category.GROCERIES,
        direction=Direction.DEBIT,
        amount=Decimal(amount),
        effective_amount=Decimal(amount),
        items=(Item(name="Cumpărături"),) if items else None,
        decision=decision,
    )


@pytest.fixture
def one_tx(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(tx: TxView) -> None:
        monkeypatch.setattr(service, "_transaction", lambda db, user_id, tx_id: tx)

    return install


@pytest.mark.parametrize(
    ("amount", "decision"),
    [
        ("500.00", Decision.ASK),
        ("300.01", Decision.ASK),
        ("300.00", Decision.AUTO),
        ("85", Decision.AUTO),
    ],
)
def test_evaluate_transaction_asks_above_300(one_tx: Any, amount: str, decision: Decision) -> None:
    one_tx(_tx(amount))
    result = service.evaluate_transaction(None, 1, 1)
    assert isinstance(result, Evaluation)
    assert result.decision == decision
    assert result.effective_amount == Decimal(amount)
    assert (result.question_hint is not None) == (decision == Decision.ASK)


def test_evaluate_transaction_provisional_reading_and_item_hint(one_tx: Any) -> None:
    one_tx(_tx("4500.00", items=False))
    result = service.evaluate_transaction(None, 1, 1)
    assert result.purpose == Purpose.UNPLANNED_DISCRETIONARY
    assert result.annotation_source == AnnotationSource.DEFAULT
    assert result.question_hint is not None
    assert result.question_hint.ask_what_item is True


def test_evaluate_auto_is_source_auto(one_tx: Any) -> None:
    one_tx(_tx("85.00"))
    assert service.evaluate_transaction(None, 1, 1).annotation_source == AnnotationSource.AUTO


def test_default_reading() -> None:
    reading = service.default_reading(_tx("120.50"))
    assert reading.purpose == Purpose.UNPLANNED_DISCRETIONARY
    assert reading.confidence == 0.3
    assert reading.annotation_source == AnnotationSource.DEFAULT
    assert reading.effective_amount == Decimal("120.50")


def _day(monkeypatch: pytest.MonkeyPatch, txs: list[TxView], asked: bool) -> None:
    monkeypatch.setattr(service, "_transactions_of_day", lambda db, user_id, day: txs)
    monkeypatch.setattr(service, "_question_asked_today", lambda db, user_id, today: asked)


def test_pick_question_first_ask(monkeypatch: pytest.MonkeyPatch) -> None:
    txs = [_tx("50", tx_id=1, decision=Decision.AUTO), _tx("500", tx_id=2, decision=Decision.ASK),
           _tx("700", tx_id=3, decision=Decision.ASK)]  # fmt: skip
    _day(monkeypatch, txs, asked=False)
    candidate = service.pick_question(None, 1, TODAY)
    assert isinstance(candidate, QuestionCandidate)
    assert candidate.transaction_id == 2


def test_pick_question_none_when_asked_today_or_nothing_to_ask(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _day(monkeypatch, [_tx("500", decision=Decision.ASK)], asked=True)
    assert service.pick_question(None, 1, TODAY) is None
    _day(monkeypatch, [_tx("50", decision=Decision.AUTO)], asked=False)
    assert service.pick_question(None, 1, TODAY) is None


def test_the_other_stubs() -> None:
    occupation = fact(FactType.OCCUPATION, id=7)
    assert service.signatures_for_fact(occupation, None) == []
    assert service.on_fact_changed(None, 1, 7) == PropagationResult(fact_id=7)
    assert service.learn_from_annotation(None, 1, 1) is None
    assert service.infer_hypotheses(None, 1) == []


def test_services_are_looked_up_at_call_time() -> None:
    # B3 isn't merged: the stub fails clearly at call time, not at import.
    with pytest.raises(ModuleNotFoundError, match=r"app\.services"):
        service.evaluate_transaction(None, 1, 1)
