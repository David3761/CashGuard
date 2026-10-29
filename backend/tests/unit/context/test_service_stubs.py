"""S0: the context layer's §15 stubs are importable and return the documented types."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app import clock
from app.context import library, service
from app.context.evaluate import evaluate
from app.domain.enums import AnnotationSource, Category, Decision, Direction, FactType, Purpose
from app.domain.models import Item, TxView
from app.domain.results import PropagationResult, QuestionCandidate
from app.domain.user_context import UserContext
from tests import builders
from tests.builders import fact

TODAY = date(2026, 6, 15)
NOON = datetime(2026, 6, 15, 11, 0, tzinfo=UTC)  # 14:00 in Bucharest


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


@pytest.fixture
def matei(monkeypatch: pytest.MonkeyPatch) -> UserContext:
    ctx = builders.matei_ctx()
    monkeypatch.setattr(service, "_context", lambda db, user_id, today: ctx)
    return ctx


def test_evaluate_transaction_runs_the_pure_core(one_tx: Any, matei: UserContext) -> None:
    tx = builders.tx(id=700, amount="500", effective_amount="500", decision=None)
    one_tx(tx)
    with clock.use_clock(clock.FixedClock(NOON)):
        result = service.evaluate_transaction(None, 1, 700)
    assert result == evaluate(matei, tx)
    assert result.decision == Decision.ASK


def test_default_reading() -> None:
    reading = service.default_reading(_tx("120.50"))
    assert reading.purpose == Purpose.UNPLANNED_DISCRETIONARY
    assert reading.confidence == 0.3
    assert reading.annotation_source == AnnotationSource.DEFAULT
    assert reading.effective_amount == Decimal("120.50")


def test_pick_question_asks_the_waiting_transaction(
    monkeypatch: pytest.MonkeyPatch, matei: UserContext
) -> None:
    waiting = builders.tx(id=701, amount="500", effective_amount="500", decision="ask",
                          unexplained=0.8)  # fmt: skip
    days = {TODAY: [waiting, builders.tx(id=702, decision="auto")]}
    monkeypatch.setattr(service, "_transactions_of_day", lambda db, u, day: days.get(day, []))
    with clock.use_clock(clock.FixedClock(NOON)):
        candidate = service.pick_question(None, 1, TODAY)
    assert isinstance(candidate, QuestionCandidate)
    assert candidate.transaction_id == 701
    asked = matei.replace(questions_asked_today=1)
    monkeypatch.setattr(service, "_context", lambda db, user_id, today: asked)
    with clock.use_clock(clock.FixedClock(NOON)):
        assert service.pick_question(None, 1, TODAY) is None


def test_the_other_stubs() -> None:
    occupation = fact(FactType.OCCUPATION, id=7)
    assert service.signatures_for_fact(occupation, None) == library.signatures_for_fact(occupation)
    assert service.on_fact_changed(None, 1, 7) == PropagationResult(fact_id=7)
    assert service.learn_from_annotation(None, 1, 1) is None


def _fuel(day: int) -> TxView:
    return builders.tx(
        id=800 + day,
        occurred_at=builders.at(date(2026, 6, day), 18),
        merchant_raw="PETROM 112",
        merchant="Petrom",
        merchant_id="petrom",
        mcc="5541",
        category="fuel",
        amount="250",
        effective_amount="250",
    )


class _LifeFacts:
    def __init__(self, rejected: list[Any]) -> None:
        self.rejected = rejected

    def list_rejected(self, db: Any, user_id: int) -> list[Any]:
        return self.rejected


def test_infer_hypotheses_runs_the_pure_core_with_the_rejected_facts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weekly_fuel = builders.ctx(transactions=[_fuel(1), _fuel(8), _fuel(14)])
    monkeypatch.setattr(service, "_context", lambda db, user_id, today: weekly_fuel)
    life_facts = _LifeFacts([])
    monkeypatch.setattr(service, "_service", lambda name: life_facts)
    with clock.use_clock(clock.FixedClock(NOON)):
        [draft] = service.infer_hypotheses(None, 5)
        assert draft.type is FactType.VEHICLE
        life_facts.rejected = [fact(FactType.VEHICLE, status="rejected")]
        assert service.infer_hypotheses(None, 5) == []


def test_infer_hypotheses_without_list_rejected_still_runs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    weekly_fuel = builders.ctx(transactions=[_fuel(1), _fuel(8), _fuel(14)])
    monkeypatch.setattr(service, "_context", lambda db, user_id, today: weekly_fuel)
    monkeypatch.setattr(service, "_service", lambda name: object())
    with clock.use_clock(clock.FixedClock(NOON)):
        assert [d.type for d in service.infer_hypotheses(None, 5)] == [FactType.VEHICLE]


def test_services_are_looked_up_at_call_time() -> None:
    # B3 isn't merged: the stub fails clearly at call time, not at import.
    with pytest.raises(ModuleNotFoundError, match=r"app\.services"):
        service.evaluate_transaction(None, 1, 1)
