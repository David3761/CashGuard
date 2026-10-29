"""A3 step 2: annotate_transaction / apply_annotation, receivables, offer_payment_request."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from app.agent.executor import ToolEntry, execute_tool
from app.agent.handlers import receivables, transactions
from app.agent.handlers.registry import HANDLERS
from app.clock import FixedClock, use_clock
from app.domain.enums import (
    AnnotationSource,
    Beneficiary,
    Purpose,
    ReceivableStatus,
)
from app.errors import DomainError
from tests.fakes.fake_services import FakeAgentEvents, FakeReceivables, Harness

D = Decimal


@pytest.fixture(autouse=True)
def _clock() -> Any:
    with use_clock(FixedClock(datetime(2026, 10, 28, 14, 0, tzinfo=UTC))) as c:
        yield c


def _h(**kw: Any) -> Harness:
    h = Harness(**kw)
    h.add_tx(918, "500.00")
    return h


async def _annotate(
    h: Harness,
    *,
    purpose: Purpose = Purpose.ON_BEHALF_OF_OTHERS,
    beneficiary: Beneficiary = Beneficiary.SHARED,
    tx_id: int = 918,
    **kw: Any,
) -> transactions.AnnotationResult:
    return await transactions.apply_annotation(
        None,
        h.user_id,
        tx_id,
        purpose,
        beneficiary,
        **kw,
        services=h.services,
        engine=h.engine,
        context=h.context,
    )


def _rcv(h: Harness) -> FakeReceivables:
    r = h.services.receivables
    assert isinstance(r, FakeReceivables)
    return r


async def test_five_people_gives_100_and_a_receivable_of_400() -> None:
    h = _h()
    result = await _annotate(h, people_count=5, others_will_repay=True, debtor_label="colegi")
    assert result.effective_amount == D("100.00")
    assert result.receivable_amount == D("400.00")
    assert result.amount_each == D("100.00")
    assert result.estimated is False
    tx = await h.services.transactions.get(1, 918)
    assert tx.effective_amount == D("100.00")
    assert tx.annotation_source is AnnotationSource.ANSWER
    rcv = await _rcv(h).get(1, result.receivable_id or 0)
    assert (rcv.amount, rcv.debtor_label, rcv.status) == (D("400.00"), "colegi", "open")
    assert rcv.expected_by == date(2026, 11, 11)
    assert tx.receivable_id == rcv.id
    assert ("on_annotation_changed", (1, 918, D("500.00"), D("100.00"))) in h.engine.calls
    [(before, after)] = h.engine.views  # danutu's E3 reads the views (purpose, pot, amount)
    assert before is not None
    assert after is not None
    assert (before.effective_amount, before.purpose) == (D("500.00"), None)
    assert (after.effective_amount, after.purpose) == (D("100.00"), Purpose.ON_BEHALF_OF_OTHERS)
    assert h.context.names() == ["learn_from_annotation"]


async def test_own_amount_wins_over_people_count() -> None:
    h = _h()
    result = await _annotate(h, own_amount=D("120"), people_count=5, others_will_repay=True)
    assert result.effective_amount == D("120.00")
    assert result.receivable_amount == D("380.00")
    assert result.amount_each == D("95.00")
    assert (await _rcv(h).get(1, result.receivable_id or 0)).debtor_label == "alții"


@pytest.mark.parametrize("own", [D("500.01"), D("-1")])
async def test_own_amount_outside_the_amount_is_an_error(own: Decimal) -> None:
    h = _h()
    with pytest.raises(DomainError) as error:
        await _annotate(h, own_amount=own)
    assert error.value.code == "invalid_own_amount"
    assert (await h.services.transactions.get(1, 918)).effective_amount == D("500.00")  # unchanged


async def test_one_person_means_no_receivable() -> None:
    h = _h()
    result = await _annotate(h, people_count=1, others_will_repay=True)
    assert result.effective_amount == D("500.00")
    assert result.receivable_id is None
    assert await _rcv(h).list_open(1) == []


async def test_neither_count_nor_amount_is_estimated_and_clamped() -> None:
    h = _h()
    h.engine.estimate = D("120")
    result = await _annotate(h, others_will_repay=True)
    assert (result.effective_amount, result.estimated) == (D("120.00"), True)
    assert result.receivable_amount == D("380.00")
    h.engine.estimate = D("9999")
    assert (await _annotate(h)).effective_amount == D("500.00")  # clamped to the amount


async def test_for_myself_only_is_the_whole_amount_without_an_estimate() -> None:
    h = _h()
    result = await _annotate(
        h, purpose=Purpose.UNPLANNED_DISCRETIONARY, beneficiary=Beneficiary.SELF
    )
    assert (result.effective_amount, result.estimated) == (D("500.00"), False)
    assert "own_share_estimate" not in h.engine.names()


async def test_a_correction_cancels_the_receivable_with_the_right_ledger_delta() -> None:
    h = _h()
    first = await _annotate(h, people_count=5, others_will_repay=True, debtor_label="colegi")
    fix = await _annotate(h, purpose=Purpose.UNPLANNED_DISCRETIONARY, beneficiary=Beneficiary.SELF)
    assert fix.cancelled_receivable_id == first.receivable_id
    assert fix.previous_effective_amount == D("100.00")
    assert fix.effective_amount == D("500.00")
    assert (await _rcv(h).get(1, first.receivable_id or 0)).status is ReceivableStatus.CANCELLED
    assert h.engine.calls[-1] == ("on_annotation_changed", (1, 918, D("100.00"), D("500.00")))
    assert (await h.services.transactions.get(1, 918)).receivable_id is None


async def test_the_same_answer_twice_keeps_one_receivable() -> None:
    h = _h()
    a = await _annotate(h, people_count=5, others_will_repay=True, debtor_label="colegi")
    b = await _annotate(h, people_count=5, others_will_repay=True, debtor_label="colegi")
    assert a.receivable_id == b.receivable_id
    assert b.cancelled_receivable_id is None
    assert len(await _rcv(h).list_open(1)) == 1


async def test_another_users_transaction_is_not_found() -> None:
    h = Harness(user_id=1)
    h.add_tx(918, "500.00", user_id=2)
    with pytest.raises(DomainError) as error:
        await _annotate(h, people_count=5, others_will_repay=True)
    assert error.value.code == "not_found"


async def test_the_open_question_is_marked_answered() -> None:
    h = _h()
    events = h.services.agent_events
    assert isinstance(events, FakeAgentEvents)
    event = await events.create(1, {"ref_transaction_id": 918, "status": "asked"})
    result = await _annotate(h, people_count=5, others_will_repay=True)
    assert result.answered_event_id == event["id"]
    assert (await events.get(1, event["id"]))["status"] == "answered"


# ── through the executor (registered handlers, D18) ──────────────────────────────────────────


class AnnotateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transaction_id: int
    purpose: Purpose
    beneficiary: Beneficiary
    own_amount: Decimal | None = None
    people_count: int | None = None
    others_will_repay: bool = False
    debtor_label: str | None = None
    note: str | None = None


class ReceivableIdIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    receivable_id: int


REGISTRY = {
    "annotate_transaction": ToolEntry(
        "annotate_transaction", AnnotateIn, HANDLERS["annotate_transaction"], money=True
    ),
    "offer_payment_request": ToolEntry(
        "offer_payment_request", ReceivableIdIn, HANDLERS["offer_payment_request"]
    ),
    "mark_receivable_paid": ToolEntry(
        "mark_receivable_paid", ReceivableIdIn, HANDLERS["mark_receivable_paid"], money=True
    ),
    "cancel_receivable": ToolEntry(
        "cancel_receivable", ReceivableIdIn, HANDLERS["cancel_receivable"], money=True
    ),
}


async def _call(h: Harness, name: str, tool_input: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
    out = await execute_tool(
        h.ctx, h.run, {"id": "toolu_1", "name": name, "input": tool_input}, REGISTRY
    )
    return bool(out.get("is_error")), json.loads(out["content"])


async def test_scene_a_annotate_returns_plan_forecast_then_a_payment_card() -> None:
    h = _h()
    failed, body = await _call(
        h,
        "annotate_transaction",
        {
            "transaction_id": 918,
            "purpose": "on_behalf_of_others",
            "beneficiary": "shared",
            "people_count": 5,
            "others_will_repay": True,
            "debtor_label": "colegi",
        },
    )
    assert not failed
    assert (body["effective_amount"], body["receivable_amount"], body["amount_each"]) == (
        100.0,
        400.0,
        100.0,
    )
    assert body["plan"]["previous_today_budget"] == 31.2
    assert (body["forecast"]["probability"], body["forecast"]["previous_probability"]) == (
        0.77,
        0.71,
    )
    reason = h.engine.calls[-2][1][1]
    assert reason.startswith("annotation: tx 918 500.00 → 100.00")
    assert h.engine.calls[-2][1][2] == {
        "tool": "annotate_transaction",
        "tool_use_id": "toolu_1",
        "transaction_id": 918,
    }
    assert [p[0] for p in h.run.pushes] == ["transaction.annotated", "receivable.updated"]

    failed, card = await _call(h, "offer_payment_request", {"receivable_id": body["receivable_id"]})
    assert not failed
    assert card["status"] == "open"
    assert card["card"] == {
        "type": "request_payment",
        "receivable_id": body["receivable_id"],
        "label": "Trimite cererea (4 \u00d7 100 lei)",
    }
    assert h.run.action_cards == [card["card"]]
    assert (await _rcv(h).get(1, body["receivable_id"])).status is ReceivableStatus.OPEN


async def test_offer_payment_request_on_a_paid_receivable_is_an_error() -> None:
    h = _h()
    rid = (await _annotate(h, people_count=5, others_will_repay=True)).receivable_id
    assert not (await _call(h, "mark_receivable_paid", {"receivable_id": rid}))[0]
    failed, body = await _call(h, "offer_payment_request", {"receivable_id": rid})
    assert failed
    assert body["error"]["code"] == "receivable_not_open"
    assert h.run.action_cards == []
    failed, body = await _call(h, "cancel_receivable", {"receivable_id": rid})
    assert body["error"]["code"] == "receivable_closed"


async def test_another_users_receivable_is_not_found() -> None:
    h = Harness(user_id=2)
    h.add_tx(5, "500.00")
    rid = (
        await transactions.apply_annotation(
            None,
            2,
            5,
            Purpose.ON_BEHALF_OF_OTHERS,
            Beneficiary.SHARED,
            people_count=5,
            others_will_repay=True,
            services=h.services,
            engine=h.engine,
            context=h.context,
        )
    ).receivable_id
    intruder = Harness(user_id=1, services=h.services)
    failed, body = await _call(intruder, "offer_payment_request", {"receivable_id": rid or 0})
    assert failed
    assert body["error"]["code"] == "not_found"


async def test_create_receivable_splits_a_transaction() -> None:
    h = _h()
    result = await receivables.create_receivable(
        h.ctx, h.run, {"transaction_id": 918, "people_count": 3, "debtor_label": "Andrei"}
    )
    assert result["receivable"]["amount"] == 333.33
    assert result["receivable"]["amount_each"] == 166.67
    with pytest.raises(DomainError):
        await receivables.create_receivable(h.ctx, h.run, {"debtor_label": "Andrei"})


async def test_get_transaction_reads_only_the_users_own() -> None:
    h = _h()
    assert (await transactions.get_transaction(h.ctx, h.run, {"transaction_id": 918}))[
        "transaction"
    ]["amount"] == 500.0
    h.add_tx(919, "10.00", user_id=2)
    with pytest.raises(DomainError) as error:
        await transactions.get_transaction(h.ctx, h.run, {"transaction_id": 919})
    assert error.value.code == "not_found"
