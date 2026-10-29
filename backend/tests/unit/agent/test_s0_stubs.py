"""S0: the agent's §15 stubs are importable and return the documented types."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.agent.handlers import transactions as handlers
from app.agent.language import detect_language
from app.agent.proactive import run_proactive
from app.agent.snapshot import build_snapshot
from app.clock import FixedClock, use_clock
from app.domain.enums import AnnotationSource, Beneficiary, Direction, Language, Purpose
from app.domain.models import TxView
from app.domain.results import AgentResult
from app.errors import DomainError


def test_run_proactive_template_question() -> None:
    result = run_proactive(1, 9)
    assert isinstance(result, AgentResult)
    assert result.speak_text
    assert len(result.quick_replies) >= 3


@pytest.mark.parametrize("current", list(Language))
def test_detect_language_keeps_current(current: Language) -> None:
    assert detect_language("I bought it for my colleagues", current) == current


def test_build_snapshot_minimal_text() -> None:
    with use_clock(FixedClock(datetime(2026, 6, 15, 9, 0, tzinfo=UTC))):
        text = build_snapshot(None, 3, "chat", 12)
    assert "2026-06-15" in text
    assert "chat" in text
    assert "12" in text


@pytest.fixture
def mega_500(monkeypatch: pytest.MonkeyPatch) -> None:
    tx = TxView(
        id=5, occurred_at=datetime(2026, 6, 15, 10, 5, tzinfo=UTC), merchant_raw="MEGA IMAGE 0451",
        direction=Direction.DEBIT, amount=Decimal("500.00"), effective_amount=Decimal("500.00"),
    )  # fmt: skip
    monkeypatch.setattr(handlers, "_transaction", lambda db, user_id, tx_id: tx)


@pytest.mark.usefixtures("mega_500")
def test_apply_annotation_five_people() -> None:
    result = handlers.apply_annotation(
        None, 1, 5, Purpose.SOCIAL_CONNECTION, Beneficiary.SHARED,
        people_count=5, others_will_repay=True, debtor_label="colegi",
    )  # fmt: skip
    assert isinstance(result, handlers.AnnotationResult)
    assert result.effective_amount == Decimal("100.00")
    assert result.receivable_amount == Decimal("400.00")
    assert result.amount_each == Decimal("100.00")
    assert result.source == AnnotationSource.ANSWER


@pytest.mark.usefixtures("mega_500")
def test_apply_annotation_own_amount_wins_and_bounds() -> None:
    both = handlers.apply_annotation(
        None, 1, 5, Purpose.SOCIAL_CONNECTION, Beneficiary.SHARED,
        own_amount=Decimal("120"), people_count=5, others_will_repay=True,
    )  # fmt: skip
    assert both.effective_amount == Decimal("120.00")
    assert both.receivable_amount == Decimal("380.00")
    alone = handlers.apply_annotation(None, 1, 5, Purpose.UNPLANNED_DISCRETIONARY, Beneficiary.SELF)
    assert alone.effective_amount == Decimal("500.00")
    assert alone.receivable_amount is None
    with pytest.raises(DomainError) as error:
        handlers.apply_annotation(
            None, 1, 5, Purpose.SELF_INVESTMENT, Beneficiary.SELF, own_amount=Decimal("500.01")
        )
    assert error.value.code == "invalid_own_amount"
