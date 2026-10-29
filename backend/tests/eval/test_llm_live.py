"""A1 step 5: real Claude, on purpose only (`uv run pytest -m live tests/eval`). Costs money.

Without ANTHROPIC_API_KEY (env or backend/.env) every test skips. Four tiny requests in total.
The fallback test runs with both settings, so we learn whether our key accepts the beta (D45).
"""

from collections.abc import AsyncIterator, Callable

import pytest
from anthropic.types.beta import BetaMessageParam, BetaToolParam

from app.agent.llm import LLM
from app.config import Settings

pytestmark = pytest.mark.live

PING: BetaToolParam = {
    "name": "ping",
    "description": "Check that the tool channel works. Call it when you are asked to ping.",
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}


@pytest.fixture
async def live_llm() -> AsyncIterator[Callable[[bool], LLM]]:
    settings = Settings()
    if settings.ANTHROPIC_API_KEY is None:
        pytest.skip("ANTHROPIC_API_KEY is not set: live test skipped")
    made: list[LLM] = []

    def make(refusal_fallback: bool) -> LLM:
        llm = LLM.from_settings(
            settings.model_copy(update={"ANTHROPIC_REFUSAL_FALLBACK": refusal_fallback})
        )
        made.append(llm)
        return llm

    yield make
    for llm in made:
        await llm.aclose()


@pytest.mark.parametrize("refusal_fallback", [False, True], ids=["fallback off", "fallback on"])
async def test_live_tiny_request_ends_turn(
    live_llm: Callable[[bool], LLM], refusal_fallback: bool
) -> None:
    reply = await live_llm(refusal_fallback).create(
        ["Reply with exactly one word."], [{"role": "user", "content": "Say OK."}]
    )

    assert reply.stop_reason == "end_turn"
    assert any(block.type == "text" and block.text.strip() for block in reply.content)
    assert reply.usage.input_tokens > 0


async def test_live_tool_round_trip_accepts_the_echoed_content(
    live_llm: Callable[[bool], LLM],
) -> None:
    llm = live_llm(False)
    system = ["You must call the ping tool exactly once, then reply with one word."]
    user: BetaMessageParam = {"role": "user", "content": "Ping, please."}

    first = await llm.create(system, [user], [PING])
    assert first.stop_reason == "tool_use"
    call = next(block for block in first.content if block.type == "tool_use")
    history: list[BetaMessageParam] = [
        user,
        {"role": "assistant", "content": first.content},  # thinking blocks included, unchanged
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": call.id, "content": "pong"}],
        },
    ]
    second = await llm.create(system, history, [PING])

    assert second.stop_reason == "end_turn"
