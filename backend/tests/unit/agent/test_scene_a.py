"""Scene A end-to-end through our real pieces: A4 snapshot, A2 tools, A3 executor, A6 loop.

Matei's open question on tx 918 (Mega Image, 500 lei); he answers "suntem cinci" and Claude
(FakeLLM, strict) annotates the split and offers the payment request.
"""

import json
import sys
import types
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from anthropic.types.beta import BetaMessageParam

from app.agent.executor import execute_tool
from app.agent.handlers.common import RunState, ToolContext
from app.agent.loop import run_agent
from app.agent.ports import LazyEngine
from app.agent.style import find_banned
from app.agent.wiring import AgentWiring, tool_context_factory
from app.domain.enums import AgentEventStatus, AgentEventType, Purpose
from app.domain.models import AgentEventView, TxView
from app.domain.user_context import UserContext
from app.engine import service as engine_service
from tests.builders import matei_ctx, tx
from tests.fakes.fake_llm import FakeLLM, end_turn, tool_round, tool_use
from tests.fakes.fake_services import FakeReceivables, FakeTransactions, Harness

REPLY = "Am înțeles! Cheltuiala ta reală e 100 de lei. Ai 400 de lei de recuperat de la colegi."


def _scene_a_context() -> UserContext:
    base = matei_ctx()
    mega = tx(id=918, amount="500", effective_amount="500")
    question = AgentEventView(
        id=77,
        type=AgentEventType.TRANSACTION_QUESTION,
        status=AgentEventStatus.ASKED,
        payload={"reason": "~6x the usual basket at Mega", "ask_what_item": False},
        ref_transaction_id=918,
        created_at=datetime(2026, 6, 15, 10, 6, tzinfo=UTC),
    )
    return base.model_copy(
        update={"transactions": (*base.transactions, mega), "agent_events": (question,)}
    )


async def test_scene_a_end_to_end() -> None:
    harness = Harness()
    harness.add_tx(918, "500.00")
    context = _scene_a_context()

    async def load_context(user_id: int) -> UserContext:
        return context

    async def load_history(user_id: int, limit: int) -> list[BetaMessageParam]:
        return []

    wiring = AgentWiring(
        load_context=load_context,
        tool_context=lambda user_id: harness.ctx,
        load_history=load_history,
    )
    split = {
        "transaction_id": 918,
        "purpose": "on_behalf_of_others",
        "beneficiary": "shared",
        "people_count": 5,
        "others_will_repay": True,
        "debtor_label": "colegi",
    }
    fake = FakeLLM(
        [
            tool_round(tool_use("annotate_transaction", split, tool_use_id="toolu_1")),
            tool_round(tool_use("offer_payment_request", {"receivable_id": 1}, tool_use_id="t2")),
            end_turn(REPLY),
        ]
    )
    result = await run_agent(
        1, "chat", "Am luat și pentru colegi, suntem cinci.", "voice", llm=fake, services=wiring
    )
    fake.assert_consumed()

    txs, rcvs = harness.services.transactions, harness.services.receivables
    assert isinstance(txs, FakeTransactions)
    assert isinstance(rcvs, FakeReceivables)
    assert (await txs.get(1, 918)).effective_amount == Decimal("100.00")
    receivable = await rcvs.get(1, 1)
    assert receivable.amount == Decimal("400.00")
    assert receivable.amount_each == Decimal("100.00")
    assert receivable.people_count == 5
    [card] = result.action_cards
    assert card.receivable_id == 1
    assert "4" in card.label
    assert "100" in card.label
    assert result.plan_changed is True
    assert result.ref_transaction_id == 918
    assert result.text == REPLY
    assert find_banned(result.text) == []
    assert result.speak_text
    snapshot = fake.requests[0].system[2]
    assert "[tx 918]" in snapshot
    assert fake.requests[0].tools == fake.requests[2].tools  # D46


def test_the_real_tool_context_uses_the_engine_service() -> None:
    make = tool_context_factory(Harness().services)
    ctx = make(1)
    assert isinstance(ctx.engine, LazyEngine)
    assert ctx.engine._fn("recompute_plan") is engine_service.recompute_plan
    assert ctx.user_id == 1


async def test_the_real_engine_port_is_awaited() -> None:
    # LazyEngine awaits danutu's async engine shells (the S0 stubs here). C8/C9 need bomboe's DB,
    # so the context is the fake (LazyContext's awaits: test_propagate.py, test_onboarding.py).
    harness = Harness()
    harness.add_tx(918, "500.00")
    ctx = ToolContext(
        user_id=1, services=harness.services, engine=LazyEngine(), context=harness.context
    )
    run = RunState()
    shared = {"transaction_id": 918, "purpose": "on_behalf_of_others", "beneficiary": "shared"}
    out = await execute_tool(
        ctx, run, tool_use("annotate_transaction", shared, tool_use_id="toolu_1")
    )
    body = json.loads(out["content"])
    assert "is_error" not in out, body
    assert (body["effective_amount"], body["estimated"]) == (500.0, True)  # E10 stub: all his
    assert (body["plan"]["today_budget"], body["forecast"]["probability"]) == (150.0, 0.78)
    fact = {
        "type": "occupation",
        "value": {"title": "analist sportiv"},
        "text": "Sunt analist sportiv",
        "persistence": "permanent",
    }
    out = await execute_tool(ctx, run, tool_use("add_life_fact", fact, tool_use_id="toolu_2"))
    body = json.loads(out["content"])
    assert "is_error" not in out, body
    assert body["reevaluated_transaction_ids"] == []  # the fake C9
    assert body["plan"]["version"] == 1


async def test_lazy_engine_hands_danutu_the_views_before_and_after(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # danutu's E3 is on_annotation_changed(db, user_id, tx_id, old: TxView, new: TxView).
    seen: list[tuple[TxView, TxView]] = []

    async def e3(db: Any, user_id: int, tx_id: int, old: TxView, new: TxView) -> None:
        seen.append((old, new))

    monkeypatch.setattr(engine_service, "on_annotation_changed", e3)
    before = tx(id=918, amount="500", effective_amount="500")
    after = before.replace(effective_amount="100", purpose=Purpose.ON_BEHALF_OF_OTHERS)
    engine = LazyEngine()
    await engine.on_annotation_changed(
        None, 1, 918, Decimal(500), Decimal(100), before=before, after=after
    )
    assert seen.pop() == (before, after)

    async def get(db: Any, user_id: int, tx_id: int) -> TxView:  # bomboe's B3, after the write
        return after

    module = types.ModuleType("app.services.transactions")
    module.get = get  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "app.services.transactions", module)
    await engine.on_annotation_changed(None, 1, 918, Decimal(500), Decimal(100))
    old, new = seen.pop()
    assert (old.effective_amount, new.effective_amount) == (Decimal(500), Decimal(100))
    assert new.purpose is Purpose.ON_BEHALF_OF_OTHERS
