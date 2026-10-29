"""A7: proactive runs, the spoken question (FakeLLM strict, in-memory services)."""

import asyncio
import dataclasses
import logging
from collections.abc import Sequence
from decimal import Decimal

import pytest
from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaToolParam

from app.agent import proactive
from app.agent.llm import LLMUnavailable
from app.agent.proactive import ProactiveEvent, run_proactive
from app.agent.prompts import instructions_for
from app.agent.templates import QUESTION_REPLY_KEYS, quick_replies
from tests.fakes.fake_agent_services import PROACTIVE_TOOLS, FakeAgentServices, scene_a_question
from tests.fakes.fake_llm import FakeLLM, end_turn, tool_round, tool_use

QUESTION = "Am văzut 500 de lei la Mega azi, mai mult ca de obicei. Ce a fost?"
CHIPS = ["Doar pentru mine", "Și pentru alții", "Ceva plănuit", "Prefer să nu spun"]


def _services(
    *, lang: str = "ro", merchant: str = "Mega Image", ask_what_item: bool = False
) -> FakeAgentServices:
    event = ProactiveEvent(
        event_id=77,
        type="transaction_question",
        status="pending",
        ref_transaction_id=918,
        amount=Decimal(500),
        merchant=merchant,
        ask_what_item=ask_what_item,
        reason="~6× coșul obișnuit la Mega",
    )
    return FakeAgentServices(
        language=lang,
        open_question=scene_a_question(merchant=merchant, ask_what_item=ask_what_item),
        events={77: event},
    )


class SlowLLM:
    """Never answers within the proactive deadline."""

    async def create(
        self,
        system: Sequence[str],
        messages: Sequence[BetaMessageParam],
        tools: Sequence[BetaToolParam] = (),
    ) -> BetaMessage:
        await asyncio.sleep(60)
        raise AssertionError("unreachable")


async def test_a_transaction_question_is_saved_spoken_asked_and_notified() -> None:
    services = _services()
    fake = FakeLLM(
        [
            tool_round(tool_use("show_quick_replies", {"options": CHIPS}, tool_use_id="toolu_1")),
            end_turn(QUESTION),
        ]
    )
    result = await run_proactive(1, 77, llm=fake, services=services, run_id=3)
    assert result is not None
    assert result.text == QUESTION
    assert result.speak_text == QUESTION
    assert len(result.quick_replies) >= 3
    assert result.ref_transaction_id == 918
    [saved] = services.saved_messages
    assert saved["speak"] is True
    assert saved["speak_text"] == QUESTION
    assert saved["ref_transaction_id"] == 918
    assert saved["agent_event_id"] == 77
    assert services.asked_events == [77]
    assert services.notifications == [{"text": QUESTION, "opens_chat": True, "agent_event_id": 77}]
    assert fake.requests[0].tool_names == list(PROACTIVE_TOOLS)  # read-only (D22)
    assert fake.requests[0].system[1] == instructions_for("transaction_question")
    fake.assert_consumed()


async def test_missing_chips_get_the_default_ones() -> None:
    services = _services()
    result = await run_proactive(1, 77, llm=FakeLLM([end_turn(QUESTION)]), services=services)
    assert result is not None
    assert list(result.quick_replies) == quick_replies(QUESTION_REPLY_KEYS, "ro")


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("ro", "Am văzut 500 de lei la Mega Image. A fost ceva diferit de obicei?"),
        ("en", "I saw 500 lei at Mega Image. Was it something different from usual?"),
    ],
)
async def test_a_timeout_gives_the_template_question(
    monkeypatch: pytest.MonkeyPatch, lang: str, expected: str
) -> None:
    monkeypatch.setattr(proactive, "PROACTIVE_TIMEOUT_S", 0.01)
    services = _services(lang=lang)
    result = await run_proactive(1, 77, llm=SlowLLM(), services=services)
    assert result is not None
    assert result.text == expected
    assert list(result.quick_replies) == quick_replies(QUESTION_REPLY_KEYS, lang)
    assert services.saved_messages[0]["speak"] is True
    assert services.asked_events == [77]
    assert services.runs[-1][1] == "failed"


async def test_an_llm_error_and_ask_what_item_give_the_what_item_template() -> None:
    services = _services(merchant="eMAG", ask_what_item=True)
    result = await run_proactive(1, 77, llm=FakeLLM([LLMUnavailable("down")]), services=services)
    assert result is not None
    assert result.text == "Ce ți-ai luat de la eMAG?"


async def test_a_write_tool_is_refused_in_a_proactive_run() -> None:
    services = _services()
    annotate = {"transaction_id": 918, "purpose": "unknown", "beneficiary": "self"}
    fake = FakeLLM(
        [
            tool_round(tool_use("annotate_transaction", annotate, tool_use_id="toolu_1")),
            end_turn(QUESTION),
        ]
    )
    result = await run_proactive(1, 77, llm=fake, services=services)
    content = fake.requests[1].messages[-1]["content"]
    assert isinstance(content, list)
    [refused] = content
    assert refused["is_error"] is True
    assert services.executed == []
    assert services.transactions[918].purpose is None
    assert result is not None
    assert result.text == QUESTION
    fake.assert_consumed()


async def test_the_same_event_twice_gives_no_duplicate() -> None:
    services = _services()
    first = await run_proactive(1, 77, llm=FakeLLM([end_turn(QUESTION)]), services=services)
    second = await run_proactive(1, 77, llm=FakeLLM([]), services=services)
    assert first is not None
    assert second is None
    assert len(services.saved_messages) == 1
    assert len(services.notifications) == 1


async def test_concurrent_runs_of_one_event_say_it_once() -> None:
    services = _services()
    fake = FakeLLM([end_turn(QUESTION)], strict=False)
    results = await asyncio.gather(
        run_proactive(1, 77, llm=fake, services=services),
        run_proactive(1, 77, llm=fake, services=services),
    )
    assert sum(r is not None for r in results) == 1
    assert len(services.saved_messages) == 1


async def test_a_long_question_is_logged(caplog: pytest.LogCaptureFixture) -> None:
    long_question = "Am văzut " + "o plată foarte mare " * 6 + "azi. Ce a fost?"
    with caplog.at_level(logging.WARNING, logger="app.agent.proactive"):
        result = await run_proactive(
            1, 77, llm=FakeLLM([end_turn(long_question)]), services=_services()
        )
    assert result is not None
    assert result.text == long_question  # logged, not refused
    assert any("words" in record.getMessage() for record in caplog.records)


# ── the audit row (agent_runs), like a chat run's ───────────────────────────────────────────


async def test_a_pipeline_run_opens_its_run_links_its_tool_calls_and_completes_it() -> None:
    services = _services()
    services.new_run_id = 41
    fake = FakeLLM(
        [
            tool_round(tool_use("show_quick_replies", {"options": CHIPS}, tool_use_id="toolu_1")),
            end_turn(QUESTION),
        ]
    )
    assert await run_proactive(1, 77, llm=fake, services=services) is not None
    assert services.started_runs == [1]
    assert services.tool_run_ids == [41]
    assert services.runs == [(41, "completed", None)]


async def test_a_callers_run_id_opens_no_second_run() -> None:
    services = _services()
    await run_proactive(1, 77, llm=FakeLLM([end_turn(QUESTION)]), services=services, run_id=3)
    assert services.started_runs == []
    assert services.runs == [(3, "completed", None)]


async def test_an_event_that_isnt_pending_opens_no_run() -> None:
    services = _services()
    services.events[77] = dataclasses.replace(services.events[77], status="asked")
    assert await run_proactive(1, 77, llm=FakeLLM([]), services=services) is None
    assert services.started_runs == []
    assert services.runs == []


async def test_a_run_that_raises_is_finished_as_failed() -> None:
    services = _services()
    services.new_run_id = 41

    async def broken(user_id: int, **fields: object) -> int:
        raise RuntimeError("db down")

    services.save_assistant_message = broken  # type: ignore[method-assign]
    with pytest.raises(RuntimeError):
        await run_proactive(1, 77, llm=FakeLLM([end_turn(QUESTION)]), services=services)
    assert services.runs == [(41, "failed", "internal_error")]
