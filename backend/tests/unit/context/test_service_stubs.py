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


def _returning(value: Any) -> Any:
    async def fake(*_: Any, **__: Any) -> Any:
        return value

    return fake


@pytest.fixture
def one_tx(monkeypatch: pytest.MonkeyPatch) -> Any:
    def install(tx: TxView) -> None:
        monkeypatch.setattr("app.context.service.transactions_service.get", _returning(tx))

    return install


@pytest.fixture
def matei(monkeypatch: pytest.MonkeyPatch) -> UserContext:
    ctx = builders.matei_ctx()
    monkeypatch.setattr(service, "load_user_context", _returning(ctx))
    return ctx


async def test_evaluate_transaction_runs_the_pure_core(one_tx: Any, matei: UserContext) -> None:
    tx = builders.tx(id=700, amount="500", effective_amount="500", decision=None)
    one_tx(tx)
    with clock.use_clock(clock.FixedClock(NOON)):
        result = await service.evaluate_transaction(None, 1, 700)  # type: ignore[arg-type]
    assert result == evaluate(matei, tx)
    assert result.decision == Decision.ASK


def test_default_reading() -> None:
    reading = service.default_reading(_tx("120.50"))
    assert reading.purpose == Purpose.UNPLANNED_DISCRETIONARY
    assert reading.confidence == 0.3
    assert reading.annotation_source == AnnotationSource.DEFAULT
    assert reading.effective_amount == Decimal("120.50")


async def test_pick_question_asks_the_waiting_transaction(
    monkeypatch: pytest.MonkeyPatch, matei: UserContext
) -> None:
    waiting = builders.tx(id=701, amount="500", effective_amount="500", decision="ask",
                          unexplained=0.8)  # fmt: skip
    recent = [waiting, builders.tx(id=702, decision="auto")]
    monkeypatch.setattr(
        "app.context.service.transactions_service.list_effective", _returning(recent)
    )
    with clock.use_clock(clock.FixedClock(NOON)):
        candidate = await service.pick_question(None, 1, TODAY)  # type: ignore[arg-type]
    assert isinstance(candidate, QuestionCandidate)
    assert candidate.transaction_id == 701
    asked = matei.replace(questions_asked_today=1)
    monkeypatch.setattr(service, "load_user_context", _returning(asked))
    with clock.use_clock(clock.FixedClock(NOON)):
        assert await service.pick_question(None, 1, TODAY) is None  # type: ignore[arg-type]


async def test_the_other_stubs() -> None:
    occupation = fact(FactType.OCCUPATION, id=7)
    assert service.signatures_for_fact(occupation, None) == library.signatures_for_fact(occupation)
    assert await service.on_fact_changed(None, 1, 7) == PropagationResult(fact_id=7)  # type: ignore[arg-type]
    assert await service.learn_from_annotation(None, 1, 1) is None  # type: ignore[arg-type]
    assert await service.infer_hypotheses(None, 1) == []  # type: ignore[arg-type]
