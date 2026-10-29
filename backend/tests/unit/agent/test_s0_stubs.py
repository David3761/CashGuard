"""S0: the agent's §15 stubs are importable and return the documented types."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.agent.handlers import transactions as handlers
from app.agent.language import detect_language
from app.agent.snapshot import build_snapshot
from app.clock import FixedClock, use_clock
from app.domain.enums import AnnotationSource, Beneficiary, Direction, Language, Purpose
from app.domain.models import TxView
from app.errors import DomainError


@pytest.mark.parametrize("current", list(Language))
def test_detect_language_keeps_current(current: Language) -> None:
    assert detect_language("I bought it for my colleagues", current) == current


async def test_build_snapshot_is_the_async_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    # A4 replaced the stub: the shell loads the context (B4) and renders it (tests: test_snapshot).
    from app.agent import snapshot
    from tests.builders import matei_ctx

    async def load(db: object, user_id: int, today: object) -> object:
        return matei_ctx()

    monkeypatch.setattr(snapshot, "_load_context", load)
    with use_clock(FixedClock(datetime(2026, 6, 15, 9, 0, tzinfo=UTC))):
        text = await build_snapshot(None, 1, "chat", None)
    assert "2026-06-15" in text
    assert "run: chat" in text


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
