"""Scene A end-to-end through our real pieces: A4 snapshot, A2 tools, A3 executor, A6 loop.

Matei's open question on tx 918 (Mega Image, 500 lei); he answers "suntem cinci" and Claude
(FakeLLM, strict) annotates the split and offers the payment request.
"""

from datetime import UTC, datetime
from decimal import Decimal

from anthropic.types.beta import BetaMessageParam

from app.agent.loop import run_agent
from app.agent.style import find_banned
from app.agent.wiring import AgentWiring
from app.domain.enums import AgentEventStatus, AgentEventType
from app.domain.models import AgentEventView
from app.domain.user_context import UserContext
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
    assert txs.get(1, 918).effective_amount == Decimal("100.00")
    receivable = rcvs.get(1, 1)
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
