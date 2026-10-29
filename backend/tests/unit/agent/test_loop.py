"""A6: the agent loop with FakeLLM (strict) and in-memory services."""

import json
from typing import Any

import pytest
from anthropic.types.beta import BetaMessageParam

from app.agent.llm import LLMBadRequest, LLMUnavailable
from app.agent.loop import HISTORY_LIMIT, PROACTIVE_TURN, run_agent, speak_text_for
from app.agent.prompts import instructions_for, system_rules
from app.agent.style import find_banned
from app.agent.templates import fallback_reply
from tests.fakes.fake_agent_services import SNAPSHOT, FakeAgentServices
from tests.fakes.fake_llm import (
    FakeLLM,
    cut_off,
    end_turn,
    message,
    refusal,
    text,
    thinking,
    tool_round,
    tool_use,
)


async def _run(
    fake: FakeLLM, services: FakeAgentServices, user_message: str | None = "Salut", **kw: Any
) -> Any:
    return await run_agent(
        1, kw.pop("trigger", "chat"), user_message, llm=fake, services=services, run_id=5, **kw
    )


def _results(request_messages: list[BetaMessageParam]) -> list[dict[str, Any]]:
    content = request_messages[-1]["content"]
    assert isinstance(content, list)
    return [dict(block) for block in content]


async def test_end_turn_is_the_reply() -> None:
    services = FakeAgentServices()
    fake = FakeLLM([end_turn("Bună! Ești pe drumul bun.")])
    result = await _run(fake, services)
    assert result.text == "Bună! Ești pe drumul bun."
    assert result.speak_text is None  # text input, chat run
    assert result.ref_transaction_id == 918  # the open question
    assert fake.requests[0].system == (system_rules(), instructions_for("chat"), SNAPSHOT)
    assert fake.requests[0].messages == [{"role": "user", "content": "Salut"}]
    assert services.runs == [(5, "completed", None)]
    fake.assert_consumed()


async def test_one_tool_round_appends_content_unchanged_then_the_result() -> None:
    services = FakeAgentServices()
    script = [
        tool_round(thinking(), tool_use("get_plan_status", {}, tool_use_id="toolu_1")),
        end_turn("Ai 45 de lei pe azi."),
    ]
    fake = FakeLLM(script)
    result = await _run(fake, services)
    assert result.text == "Ai 45 de lei pe azi."
    second = fake.requests[1].messages
    assert second[-2] == {"role": "assistant", "content": script[0].content}  # thinking kept
    [res] = _results(second)
    assert res["tool_use_id"] == "toolu_1"
    assert not res.get("is_error")
    assert json.loads(res["content"]) == {"daily_budget": "45.00"}
    # D46: the snapshot and the tools are built once, the same tools on every request
    assert len(services.setup_calls) == 1
    assert fake.requests[0].tools == fake.requests[1].tools
    fake.assert_consumed()


async def test_two_parallel_calls_give_one_message_with_both_results() -> None:
    services = FakeAgentServices()
    fake = FakeLLM(
        [
            tool_round(
                tool_use("get_plan_status", {}, tool_use_id="toolu_a"),
                tool_use("get_transaction", {"transaction_id": 918}, tool_use_id="toolu_b"),
            ),
            end_turn("Gata."),
        ]
    )
    await _run(fake, services)
    second = fake.requests[1].messages
    assert len(second) == 3  # user, assistant, ONE user message with all results
    assert [r["tool_use_id"] for r in _results(second)] == ["toolu_a", "toolu_b"]
    fake.assert_consumed()


@pytest.mark.parametrize(
    ("response", "reason"), [(refusal(), "refusal"), (cut_off("Am trecut tot la"), "llm_down")]
)
async def test_refusal_and_max_tokens_fall_back(response: Any, reason: str) -> None:
    services = FakeAgentServices()
    fake = FakeLLM([response])
    result = await _run(fake, services)
    assert result.text == fallback_reply(reason, "ro")  # never the partial text
    assert result.quick_replies == ()
    assert result.action_cards == ()
    assert services.runs == [(5, "failed", reason)]
    fake.assert_consumed()


async def test_unknown_stop_reason_falls_back() -> None:
    fake = FakeLLM([message(text("…"), stop_reason="pause_turn")])
    result = await _run(fake, FakeAgentServices())
    assert result.text == fallback_reply("llm_down", "ro")


async def test_six_tool_rounds_hit_the_loop_limit() -> None:
    services = FakeAgentServices()
    script = [
        tool_round(tool_use("get_plan_status", {}, tool_use_id=f"toolu_{i}")) for i in range(6)
    ]
    fake = FakeLLM(script)
    result = await _run(fake, services)
    assert result.text == fallback_reply("loop_limit", "ro")
    assert services.runs == [(5, "failed", "loop_limit")]
    fake.assert_consumed()


async def test_a_tool_error_goes_back_to_claude_as_is_error() -> None:
    services = FakeAgentServices()
    fake = FakeLLM(
        [
            tool_round(tool_use("set_goal", {"deadline": "2026-12-01"}, tool_use_id="toolu_1")),
            end_turn("Ce sumă vrei să strângi?"),
        ]
    )
    result = await _run(fake, services)
    [res] = _results(fake.requests[1].messages)
    assert res["is_error"] is True
    assert "amount" in res["content"]
    assert result.text == "Ce sumă vrei să strângi?"
    assert result.plan_changed is False
    fake.assert_consumed()


async def test_a_tool_not_offered_is_refused_before_the_executor() -> None:
    services = FakeAgentServices(tool_names=("get_plan_status",))
    fake = FakeLLM(
        [
            tool_round(
                tool_use("annotate_transaction", {"transaction_id": 918}, tool_use_id="toolu_1")
            ),
            end_turn("Bine."),
        ]
    )
    await _run(fake, services)
    [res] = _results(fake.requests[1].messages)
    assert res["is_error"] is True
    assert services.executed == []


async def test_a_banned_phrase_is_regenerated_once() -> None:
    services = FakeAgentServices()
    fake = FakeLLM([end_turn("Ai cheltuit prea mult."), end_turn("Ai cheltuit 500 de lei.")])
    result = await _run(fake, services)
    assert result.text == "Ai cheltuit 500 de lei."
    nudge = fake.requests[1].messages[-1]
    assert nudge["role"] == "user"
    assert "prea mult" in str(nudge["content"])
    fake.assert_consumed()


async def test_a_banned_phrase_twice_gives_the_template() -> None:
    fake = FakeLLM([end_turn("E risipă."), end_turn("Iar ai cheltuit.")])
    result = await _run(fake, FakeAgentServices())
    assert result.text == fallback_reply("llm_down", "ro")
    assert find_banned(result.text) == []
    fake.assert_consumed()


async def test_an_english_user_gets_the_english_fallback() -> None:
    fake = FakeLLM([refusal()])
    result = await _run(fake, FakeAgentServices(language="en"), "hello")
    assert result.text == fallback_reply("refusal", "en")


@pytest.mark.parametrize("error", [LLMUnavailable("down"), LLMBadRequest("bad")])
async def test_llm_errors_fall_back_and_change_nothing(error: Exception) -> None:
    services = FakeAgentServices()
    before = services.state()
    fake = FakeLLM([error])
    result = await _run(fake, services, "Ce mai face planul meu?")
    assert result.text == fallback_reply("llm_down", "ro")
    assert services.executed == []
    assert services.state() == before  # pending events untouched
    assert services.runs[-1][1] == "failed"


async def test_quick_replies_cards_and_plan_change_are_collected() -> None:
    services = FakeAgentServices()
    annotate = {
        "transaction_id": 918,
        "purpose": "on_behalf_of_others",
        "beneficiary": "shared",
        "people_count": 5,
        "others_will_repay": True,
        "debtor_label": "colegi",
    }
    fake = FakeLLM(
        [
            tool_round(tool_use("annotate_transaction", annotate, tool_use_id="toolu_1")),
            tool_round(
                tool_use("offer_payment_request", {"receivable_id": 9}, tool_use_id="toolu_2"),
                tool_use("show_quick_replies", {"options": ["Da", "Altă sumă"]}, tool_use_id="t3"),
            ),
            end_turn(
                "Am înțeles! Cheltuiala ta reală e **100 de lei**. Ai 400 de lei de "
                "recuperat. Șansa e 77%."
            ),
        ]
    )
    result = await _run(
        fake, services, "Am luat și pentru colegi, suntem cinci.", input_mode="voice"
    )
    assert result.quick_replies == ("Da", "Altă sumă")
    [card] = result.action_cards
    assert card.receivable_id == 9
    assert card.type == "request_payment"
    assert result.plan_changed is True
    assert result.speak_text == "Am înțeles! Cheltuiala ta reală e 100 de lei."  # 2 sentences
    fake.assert_consumed()


async def test_history_is_capped_and_the_saved_user_message_not_repeated() -> None:
    history: list[BetaMessageParam] = []
    for i in range(30):
        history.append({"role": "user", "content": f"u{i}"})
        history.append({"role": "assistant", "content": f"a{i}"})
    history.append({"role": "user", "content": "Salut"})  # B9 saved it before the run
    services = FakeAgentServices(stored_history=history)
    fake = FakeLLM([end_turn("Bună!")])
    await _run(fake, services, "Salut")
    sent = fake.requests[0].messages
    assert services.history_limits == [HISTORY_LIMIT]
    assert len(sent) <= HISTORY_LIMIT
    assert sent[0]["role"] == "user"
    assert sent[-1] == {"role": "user", "content": "Salut"}
    assert [m["content"] for m in sent].count("Salut") == 1


async def test_a_run_without_a_user_message_still_ends_with_a_user_turn() -> None:
    history: list[BetaMessageParam] = [
        {"role": "user", "content": "Salut"},
        {"role": "assistant", "content": "Bună!"},
    ]
    fake = FakeLLM([end_turn("Am văzut ceva nou.")])
    result = await _run(fake, FakeAgentServices(stored_history=history), None, trigger="proactive")
    assert fake.requests[0].messages[-1] == {"role": "user", "content": PROACTIVE_TURN}
    assert result.speak_text == "Am văzut ceva nou."  # proactive runs are spoken


def test_speak_text_is_plain_and_short() -> None:
    spoken = speak_text_for(
        "**Gata!** 🎉 Partea ta a fost ~100 de lei. Vezi [planul](x). Hai.", "ro"
    )
    assert spoken == "Gata! Partea ta a fost cam 100 de lei."
    assert len(speak_text_for("cuvânt " * 200, "en")) <= 300
