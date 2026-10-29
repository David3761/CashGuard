"""A1 steps 2 and 3: the real `LLM`: the request (arch 6.8), the streamed call, failures and logs.

No network: the SDK runs for real, but its HTTP client is an `httpx2.MockTransport` that records
every request and answers with a server-sent-event stream built from `tests/fakes/fake_llm.py`
responses. So these tests check the exact bytes that would reach the Messages API, not a mock of
our own code. (respx can't be used: it patches `httpx`, and anthropic 2.x is built on `httpx2`.)
"""

import asyncio
import copy
import inspect
import json
import logging
import os
import subprocess
import sys
import traceback
import typing
from collections.abc import AsyncIterator, Callable, Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import httpx2
import pytest
from anthropic.types.beta import (
    BetaMessage,
    BetaMessageParam,
    BetaTextBlockParam,
    BetaToolParam,
)
from hypothesis import given
from hypothesis import strategies as st
from pydantic import SecretStr

import app.agent.llm
from app.agent.llm import (
    API_BASE_URL,
    LLM,
    MAX_TOKENS_BY_EFFORT,
    REFUSAL_FALLBACK_BETA,
    TIMEOUT_S,
    LLMBadRequest,
    LLMClient,
    LLMError,
    LLMUnavailable,
    build_params,
    classify,
    get_llm,
    set_llm,
)
from app.config import Effort, Settings
from tests.fakes.fake_llm import (
    FakeLLM,
    end_turn,
    message,
    redacted_thinking,
    text,
    thinking,
    tool_use,
)

KEY = "sk-ant-test-SECRET-0123456789"
MODEL = "claude-sonnet-5-5"
RULES = "Ești un companion calm pentru bani. Nu judeci niciodată."
SNAPSHOT = "Azi: luni, 15 iunie 2026. Matei, 24 de ani, inginer junior."
SYSTEM = [RULES, SNAPSHOT]
USER: BetaMessageParam = {"role": "user", "content": "Am luat ceva de la Mega Image."}
TOOL_A: BetaToolParam = {
    "name": "get_plan_status",
    "description": "Read the current plan. Use it when the user asks how they're doing.",
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}
TOOL_B: BetaToolParam = {
    "name": "annotate_transaction",
    "description": "Record what a transaction was for. Use it after the user answers a question.",
    "input_schema": {
        "type": "object",
        "properties": {"transaction_id": {"type": "integer"}},
        "required": ["transaction_id"],
        "additionalProperties": False,
    },
    "strict": True,
}
EPHEMERAL = {"type": "ephemeral"}
# The whole request for create(SYSTEM, [USER], [TOOL_A, TOOL_B]) with the fallback off (arch 6.8).
EXPECTED_BODY: dict[str, Any] = {
    "model": MODEL,
    "max_tokens": 8000,
    "output_config": {"effort": "low"},
    "system": [
        {"type": "text", "text": RULES, "cache_control": EPHEMERAL},
        {"type": "text", "text": SNAPSHOT, "cache_control": EPHEMERAL},
    ],
    "cache_control": EPHEMERAL,  # the automatic breakpoint on the conversation tail (D48)
    "messages": [USER],
    "tools": [TOOL_A, TOOL_B],
    "stream": True,  # streamed internally: the timeout applies between chunks (review R1)
}
NEVER_SENT = {"temperature", "top_p", "top_k", "tool_choice", "thinking", "stop_sequences"}


def wire(reply: BetaMessage) -> dict[str, Any]:
    """The JSON the API sends for this response (exactly the fields the builder set)."""
    return reply.model_dump(mode="json", exclude_unset=True)


def sse(data: dict[str, Any]) -> bytes:
    """One server-sent event, as the Messages API writes it."""
    return f"event: {data['type']}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n".encode()


def sse_events(reply: BetaMessage) -> Iterator[bytes]:
    """The Messages API stream for this response, one server-sent event per item."""
    whole = wire(reply)
    event = sse

    start = {k: v for k, v in whole.items() if k not in ("stop_reason", "stop_details")}
    start |= {"content": [], "stop_reason": None, "stop_sequence": None, "stop_details": None}
    start["usage"] = {**whole["usage"], "output_tokens": 1}
    yield event({"type": "message_start", "message": start})
    for index, block in enumerate(whole["content"]):
        delta: dict[str, Any] | None = None
        opening = block
        if block["type"] == "text":
            opening, delta = (
                {"type": "text", "text": ""},
                {"type": "text_delta", "text": block["text"]},
            )
        elif block["type"] == "thinking":
            opening = {"type": "thinking", "thinking": block["thinking"], "signature": ""}
            delta = {"type": "signature_delta", "signature": block["signature"]}
        elif block["type"] == "tool_use":
            opening = {**block, "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        yield event({"type": "content_block_start", "index": index, "content_block": opening})
        if delta is not None:
            yield event({"type": "content_block_delta", "index": index, "delta": delta})
        yield event({"type": "content_block_stop", "index": index})
    stop = {"stop_reason": whole["stop_reason"], "stop_sequence": None}
    stop["stop_details"] = whole.get("stop_details")
    usage = {"output_tokens": whole["usage"]["output_tokens"]}
    yield event({"type": "message_delta", "delta": stop, "usage": usage})
    yield event({"type": "message_stop"})


SSE_HEADERS = {"content-type": "text/event-stream"}


class _Api:
    """An in-memory Messages API behind `httpx2.MockTransport`; records every HTTP request."""

    def __init__(
        self,
        *replies: BetaMessage | httpx2.Response,
        answer: Callable[[dict[str, Any]], BetaMessage] | None = None,
    ) -> None:
        self.requests: list[httpx2.Request] = []
        self._replies = list(replies)
        self._answer = answer

    def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        reply: BetaMessage | httpx2.Response
        if self._answer is not None:
            reply = self._answer(json.loads(request.content))
        else:
            reply = self._replies[len(self.requests) - 1]
        if isinstance(reply, httpx2.Response):
            return reply
        return httpx2.Response(200, headers=SSE_HEADERS, content=b"".join(sse_events(reply)))

    def http_client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(transport=httpx2.MockTransport(self._handle))

    def body(self, index: int = -1) -> dict[str, Any]:
        decoded: dict[str, Any] = json.loads(self.requests[index].content)
        return decoded


MakeLLM = Callable[..., LLM]


@pytest.fixture
async def make_llm() -> AsyncIterator[MakeLLM]:
    """Builds `LLM`s wired to an `_Api`, and closes them after the test."""
    made: list[LLM] = []

    def make(
        api: _Api,
        *,
        api_key: str | None = KEY,
        model: str = MODEL,
        effort: Effort = "low",
        refusal_fallback: bool = False,
        max_retries: int = 2,
    ) -> LLM:
        llm = LLM(
            api_key=api_key,
            model=model,
            effort=effort,
            refusal_fallback=refusal_fallback,
            max_retries=max_retries,
            http_client=api.http_client(),
        )
        made.append(llm)
        return llm

    yield make
    for llm in made:
        await llm.aclose()  # the LLM owns its HTTP client, key or no key (review R7)


@pytest.fixture
def sdk_logger_levels() -> Iterator[None]:
    """Logger levels are global: put the SDK's back exactly as they were."""
    loggers = [logging.getLogger(name) for name in ("anthropic", "httpx2")]
    levels = [logger.level for logger in loggers]
    yield
    for logger, level in zip(loggers, levels, strict=True):
        logger.setLevel(level)


# ── happy path ───────────────────────────────────────────────────────────────────────────


async def test_request_body_and_headers_are_exactly_the_arch_6_8_settings(
    make_llm: MakeLLM,
) -> None:
    api = _Api(end_turn("Bună!"))
    llm = make_llm(api)

    await llm.create(SYSTEM, [USER], [TOOL_A, TOOL_B])

    request = api.requests[0]
    assert request.method == "POST"
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert api.body() == EXPECTED_BODY
    assert NEVER_SENT.isdisjoint(api.body())
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.headers["anthropic-version"] == "2026-10-21"
    assert "anthropic-beta" not in request.headers


async def test_refusal_fallback_on_adds_the_beta_header_and_fallbacks_default(
    make_llm: MakeLLM,
) -> None:
    api = _Api(end_turn("Bună!"))
    llm = make_llm(api, refusal_fallback=True)

    await llm.create(SYSTEM, [USER], [TOOL_A, TOOL_B])

    assert api.body() == EXPECTED_BODY | {"fallbacks": "default"}
    assert api.requests[0].headers["anthropic-beta"] == "server-side-fallback-2026-07-01"
    assert REFUSAL_FALLBACK_BETA == "server-side-fallback-2026-07-01"


async def test_model_and_effort_come_from_the_configuration(make_llm: MakeLLM) -> None:
    api = _Api(end_turn("ok"))
    llm = make_llm(api, model="claude-opus-5-5", effort="medium")

    await llm.create(SYSTEM, [USER])

    assert api.body()["model"] == "claude-opus-5-5"
    assert api.body()["output_config"] == {"effort": "medium"}


async def test_the_real_client_returns_what_the_fake_returns(make_llm: MakeLLM) -> None:
    # "fake == real": A6's FakeLLM tests see exactly the objects production sees, as a plain
    # BetaMessage (not the stream helper's Parsed* subclasses).
    scripted = message(
        thinking("", signature="sig-1"),
        redacted_thinking("opaque"),
        text("Mă uit la plan."),
        tool_use("get_plan_status", {"zi": "luni"}, tool_use_id="toolu_1"),
        stop_reason="tool_use",
        cache_read=900,
        cache_write=120,
    )
    llm = make_llm(_Api(scripted))

    got = await llm.create(SYSTEM, [USER], [TOOL_A])

    assert type(got) is BetaMessage
    assert [type(block).__name__ for block in got.content] == [
        "BetaThinkingBlock",
        "BetaRedactedThinkingBlock",
        "BetaTextBlock",
        "BetaToolUseBlock",
    ]
    assert got == scripted
    assert got.usage.cache_read_input_tokens == 900


async def test_a_refusal_comes_back_with_its_category(make_llm: MakeLLM) -> None:
    refused = message(stop_reason="refusal", output_tokens=0, refusal_category="general_harms")

    got = await make_llm(_Api(refused)).create(SYSTEM, [USER])

    assert got == refused
    assert got.stop_details is not None
    assert got.stop_details.category == "general_harms"


def test_llm_satisfies_the_llm_client_protocol() -> None:
    # The real check is static: mypy (in `make check`) verifies this assignment.
    llm: LLMClient = LLM(api_key=None, model=MODEL, effort="low", refusal_fallback=False)
    assert callable(llm.create)


# ── boundaries ───────────────────────────────────────────────────────────────────────────


async def test_echoed_assistant_turn_goes_back_exactly_as_the_api_sent_it(
    make_llm: MakeLLM,
) -> None:
    # Arch 6.8: append `resp.content` unchanged (thinking signatures included), proven on the wire.
    first = message(
        thinking(signature="sig-1"),
        redacted_thinking("opaque"),
        text("Mă uit."),
        tool_use("get_plan_status", {}, tool_use_id="toolu_1"),
        stop_reason="tool_use",
    )
    api = _Api(first, end_turn("Gata."))
    llm = make_llm(api)
    reply = await llm.create(SYSTEM, [USER], [TOOL_A])
    history: list[BetaMessageParam] = [
        USER,
        {"role": "assistant", "content": reply.content},
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"ok":1}'}],
        },
    ]

    await llm.create(SYSTEM, history, [TOOL_A])

    assert api.body(1)["messages"][1] == {"role": "assistant", "content": wire(first)["content"]}


async def test_no_tools_means_no_tools_key(make_llm: MakeLLM) -> None:
    api = _Api(end_turn("ok"))

    await make_llm(api).create(SYSTEM, [USER])

    assert "tools" not in api.body()


async def test_one_system_part_is_one_cached_block(make_llm: MakeLLM) -> None:
    api = _Api(end_turn("ok"))

    await make_llm(api).create([RULES], [USER])

    assert api.body()["system"] == [{"type": "text", "text": RULES, "cache_control": EPHEMERAL}]


async def test_three_system_parts_use_all_four_cache_breakpoints(make_llm: MakeLLM) -> None:
    api = _Api(end_turn("ok"))

    await make_llm(api).create([RULES, "Instrucțiuni: întrebare proactivă.", SNAPSHOT], [USER])

    assert len(api.body()["system"]) == 3
    assert _count_cache_markers(api.body()) == 4  # the API's maximum


@pytest.mark.parametrize(
    ("system", "error"),
    [
        ([RULES, "b", "c", SNAPSHOT], ValueError),  # 4 parts + the tail = 5 breakpoints
        ([], ValueError),
        (RULES, TypeError),  # a bare str
        ([RULES, "  "], ValueError),
    ],
    ids=["4 parts", "0 parts", "bare str", "blank part"],
)
async def test_an_invalid_system_prompt_is_rejected_before_anything_is_sent(
    make_llm: MakeLLM, system: Any, error: type[Exception]
) -> None:
    api = _Api(end_turn("ok"))

    with pytest.raises(error):
        await make_llm(api).create(system, [USER])

    assert api.requests == []


@pytest.mark.parametrize("effort", typing.get_args(Effort))
async def test_max_tokens_grows_with_effort(make_llm: MakeLLM, effort: Effort) -> None:
    # Thinking counts toward max_tokens: higher effort thinks more (review R4).
    expected = {"low": 8000, "medium": 16000, "high": 32000, "xhigh": 64000, "max": 64000}
    api = _Api(end_turn("ok"))

    await make_llm(api, effort=effort).create(SYSTEM, [USER])

    assert api.body()["max_tokens"] == expected[effort] == MAX_TOKENS_BY_EFFORT[effort]
    assert expected[effort] <= 128_000  # Sonnet 5.5's output limit


def test_every_effort_level_has_a_max_tokens() -> None:
    assert set(MAX_TOKENS_BY_EFFORT) == set(typing.get_args(Effort))


# ── invalid input: cache markers the LLM doesn't own (review R2) ─────────────────────────


def _tool_with_marker() -> BetaToolParam:
    return {**TOOL_A, "cache_control": {"type": "ephemeral"}}


@pytest.mark.parametrize(
    ("messages", "tools"),
    [
        ([USER], [_tool_with_marker()]),
        (
            [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "hi", "cache_control": EPHEMERAL}],
                }
            ],
            [],
        ),
        (
            [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": "toolu_1",
                            "content": [
                                {"type": "text", "text": "{}", "cache_control": {"ttl": "1h"}}
                            ],
                        }
                    ],
                }
            ],
            [],
        ),
    ],
    ids=["on a tool", "on a message block", "inside a tool_result"],
)
async def test_a_cache_marker_from_the_caller_is_rejected_before_anything_is_sent(
    make_llm: MakeLLM, messages: list[BetaMessageParam], tools: list[BetaToolParam]
) -> None:
    # 3 system parts + the tail + 1 more = 5 → a 400; a 1 h marker before the 5 min tail → a 400.
    api = _Api(end_turn("ok"))

    with pytest.raises(ValueError, match="cache_control"):
        await make_llm(api).create([RULES], messages, tools)

    assert api.requests == []


async def test_a_schema_property_named_cache_control_is_not_a_cache_marker(
    make_llm: MakeLLM,
) -> None:
    tool: BetaToolParam = {
        "name": "set_preferences",
        "input_schema": {"type": "object", "properties": {"cache_control": {"type": "string"}}},
    }
    api = _Api(end_turn("ok"))

    await make_llm(api).create([RULES], [USER], [tool])

    assert api.body()["tools"] == [tool]


# ── error paths (missing key) and security ───────────────────────────────────────────────


@pytest.mark.parametrize("missing", [None, ""])
async def test_without_an_api_key_nothing_is_sent_and_the_llm_is_unavailable(
    make_llm: MakeLLM, monkeypatch: pytest.MonkeyPatch, missing: str | None
) -> None:
    # The SDK would otherwise fall back to env vars or an `ant auth login` profile.
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-the-environment")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "token-from-the-environment")
    api = _Api(end_turn("ok"))
    llm = make_llm(api, api_key=missing)

    with pytest.raises(LLMUnavailable, match="ANTHROPIC_API_KEY is not set"):
        await llm.create(SYSTEM, [USER])

    assert api.requests == []


async def test_an_invalid_prompt_is_reported_even_without_a_key(make_llm: MakeLLM) -> None:
    # A programming error must not hide behind "no key configured".
    llm = make_llm(_Api(), api_key=None)

    with pytest.raises(TypeError, match="not a single str"):
        await llm.create(RULES, [USER])


async def test_the_api_key_is_held_only_by_the_sdk_client(make_llm: MakeLLM) -> None:
    # Review R8: the LLM keeps no copy of the key in its own attributes or its repr.
    api = _Api(end_turn("ok"))
    llm = make_llm(api)

    await llm.create(SYSTEM, [USER])

    own = {name: value for name, value in vars(llm).items() if name != "_client"}
    assert all(KEY not in repr(value) for value in own.values())
    assert KEY not in repr(llm)
    assert KEY not in str(llm)
    assert getattr(vars(llm)["_client"], "api_key", None) == KEY
    assert KEY not in api.requests[0].content.decode()
    carrying = [name for name, value in api.requests[0].headers.items() if KEY in value]
    assert carrying == ["authorization"]


async def test_the_base_url_never_comes_from_the_environment(
    make_llm: MakeLLM, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Review R3: a stray ANTHROPIC_BASE_URL would send the key and user data elsewhere.
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://collector.example")
    api = _Api(end_turn("ok"))

    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        await make_llm(api).create(SYSTEM, [USER])

    assert API_BASE_URL == "https://api.anthropic.com"
    assert api.requests[0].url.host == "api.anthropic.com"
    assert "ANTHROPIC_BASE_URL is ignored" in caplog.text


async def test_custom_headers_from_the_environment_disable_the_client(
    make_llm: MakeLLM, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Review R3: the SDK merges ANTHROPIC_CUSTOM_HEADERS into every request (an auth header, a
    # beta, even anthropic-version); they can't be stripped safely, so the client fails closed.
    monkeypatch.setenv("ANTHROPIC_CUSTOM_HEADERS", "X-Forward-To: collector\nanthropic-beta: x")
    api = _Api(end_turn("ok"))

    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        llm = make_llm(api)
        with pytest.raises(LLMUnavailable, match="ANTHROPIC_CUSTOM_HEADERS is set"):
            await llm.create(SYSTEM, [USER])

    assert api.requests == []
    assert "ANTHROPIC_CUSTOM_HEADERS is set" in caplog.text


@pytest.mark.usefixtures("sdk_logger_levels")
async def test_anthropic_log_cannot_make_the_sdk_log_request_bodies(
    make_llm: MakeLLM, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Review R3: ANTHROPIC_LOG=debug (read when `anthropic` is imported) makes the SDK log whole
    # request bodies, i.e. user financial data. Simulate that import-time effect, then build an LLM.
    monkeypatch.setenv("ANTHROPIC_LOG", "debug")
    logging.getLogger("anthropic").setLevel(logging.DEBUG)
    logging.getLogger("httpx2").setLevel(logging.DEBUG)

    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        make_llm(_Api())

    assert logging.getLogger("anthropic").level == logging.WARNING
    assert logging.getLogger("httpx2").level == logging.WARNING
    assert "ANTHROPIC_LOG is ignored" in caplog.text


@pytest.mark.usefixtures("sdk_logger_levels")
def test_anthropic_log_never_lowers_a_stricter_sdk_level(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_LOG", "debug")
    logging.getLogger("anthropic").setLevel(logging.ERROR)
    logging.getLogger("httpx2").setLevel(logging.WARNING)

    LLM(api_key=KEY, model=MODEL, effort="low", refusal_fallback=False)

    assert logging.getLogger("anthropic").level == logging.ERROR
    assert logging.getLogger("httpx2").level == logging.WARNING


# ── ownership of the HTTP client (review R7) ─────────────────────────────────────────────


@pytest.mark.parametrize("api_key", [KEY, None], ids=["with a key", "without a key"])
async def test_aclose_closes_the_injected_http_client_key_or_no_key(api_key: str | None) -> None:
    http_client = _Api().http_client()
    llm = LLM(
        api_key=api_key,
        model=MODEL,
        effort="low",
        refusal_fallback=False,
        http_client=http_client,
    )

    await llm.aclose()

    assert http_client.is_closed


async def test_aclose_without_any_client_is_a_no_op() -> None:
    llm = LLM(api_key=None, model=MODEL, effort="low", refusal_fallback=False)

    await llm.aclose()
    await llm.aclose()  # and it's safe twice (app shutdown after a failed start)


# ── retries: a broken stream is never re-generated (review R1) ───────────────────────────


class _BrokenStream(httpx2.AsyncByteStream):
    """The first events of a reply, then the connection goes silent past the read timeout."""

    def __init__(self, reply: BetaMessage) -> None:
        self._first = next(sse_events(reply))

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self._first
        raise httpx2.ReadTimeout("no chunk within the read timeout")


async def test_a_stream_that_breaks_midway_is_not_retried(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    # A retry would pay for a whole new generation; the caller falls back instead (A1.3: the raw
    # httpx2 error from inside the stream becomes LLMUnavailable).
    calls: list[httpx2.Request] = []

    def handle(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, headers=SSE_HEADERS, stream=_BrokenStream(end_turn("x")))

    llm = LLM(
        api_key=KEY,
        model=MODEL,
        effort="low",
        refusal_fallback=False,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
    )
    try:
        with (
            caplog.at_level(logging.WARNING, logger="app.agent.llm"),
            pytest.raises(LLMUnavailable, match="unreachable") as raised,
        ):
            await llm.create(SYSTEM, [USER])
    finally:
        await llm.aclose()

    assert len(calls) == 1
    # Review A1.3 R1: no cause attached (SDK errors can hold content); the log names the failure.
    assert raised.value.__cause__ is None
    assert "Claude unreachable: ReadTimeout" in caplog.text


# ── concurrency ──────────────────────────────────────────────────────────────────────────


async def test_concurrent_calls_on_one_client_each_get_their_own_answer(
    make_llm: MakeLLM,
) -> None:
    def echo(body: dict[str, Any]) -> BetaMessage:
        return end_turn(f"ai spus: {body['messages'][-1]['content']}")

    api = _Api(answer=echo)
    llm = make_llm(api)
    users: list[BetaMessageParam] = [{"role": "user", "content": f"mesaj {i}"} for i in range(20)]

    replies = await asyncio.gather(*(llm.create(SYSTEM, [user]) for user in users))

    assert len(api.requests) == 20
    for user, reply in zip(users, replies, strict=True):
        block = reply.content[0]
        assert block.type == "text"
        assert block.text == f"ai spus: {user['content']}"


# ── idempotency ──────────────────────────────────────────────────────────────────────────


async def test_the_same_inputs_give_byte_identical_requests(make_llm: MakeLLM) -> None:
    # Byte-stable prefixes are what make the prompt cache hit (arch 6.8).
    api = _Api(end_turn("unu"), end_turn("doi"))
    llm = make_llm(api)

    await llm.create(SYSTEM, [USER], [TOOL_A, TOOL_B])
    await llm.create(SYSTEM, [USER], [TOOL_A, TOOL_B])

    assert api.requests[0].content == api.requests[1].content


async def test_create_does_not_mutate_the_callers_inputs(make_llm: MakeLLM) -> None:
    system, messages, tools = list(SYSTEM), [USER], [TOOL_A, TOOL_B]
    before = copy.deepcopy((system, messages, tools))

    await make_llm(_Api(end_turn("ok"))).create(system, messages, tools)

    assert (system, messages, tools) == before


# ── time ─────────────────────────────────────────────────────────────────────────────────


async def test_every_request_has_the_30_second_timeout(make_llm: MakeLLM) -> None:
    # Streamed, so "read" is the longest silence between two chunks, not the whole generation.
    api = _Api(end_turn("ok"))

    await make_llm(api).create(SYSTEM, [USER])

    assert TIMEOUT_S == 30.0
    timeout = api.requests[0].extensions["timeout"]
    assert timeout == {"connect": 30.0, "read": 30.0, "write": 30.0, "pool": 30.0}


# ── language ─────────────────────────────────────────────────────────────────────────────


async def test_romanian_text_and_emoji_reach_the_api_unchanged(make_llm: MakeLLM) -> None:
    system = [
        "Răspunde în limba utilizatorului: română sau engleză.",
        "Ți-ai luat ceva de la eMAG?",
    ]
    user: BetaMessageParam = {"role": "user", "content": "Și pentru colegi 🎧, cinci în total"}
    api = _Api(end_turn("Am înțeles 👍"))

    reply = await make_llm(api).create(system, [user])

    assert [block["text"] for block in api.body()["system"]] == system
    assert api.body()["messages"] == [user]
    block = reply.content[0]
    assert block.type == "text"
    assert block.text == "Am înțeles 👍"


# ── invariants ───────────────────────────────────────────────────────────────────────────


def _count_cache_markers(node: object) -> int:
    if isinstance(node, dict):
        return int("cache_control" in node) + sum(_count_cache_markers(v) for v in node.values())
    if isinstance(node, list):
        return sum(_count_cache_markers(v) for v in node)
    return 0


@given(
    parts=st.lists(st.text(min_size=1).filter(str.strip), min_size=1, max_size=3),
    fallback=st.booleans(),
    n_tools=st.integers(min_value=0, max_value=5),
    effort=st.sampled_from(typing.get_args(Effort)),
)
def test_build_params_keeps_its_shape_for_any_input(
    parts: list[str], fallback: bool, n_tools: int, effort: Effort
) -> None:
    tools: list[BetaToolParam] = [
        {"name": f"tool_{i}", "input_schema": {"type": "object"}} for i in range(n_tools)
    ]

    params = build_params(
        parts, [USER], tools, model=MODEL, effort=effort, refusal_fallback=fallback
    )

    system = cast(list[BetaTextBlockParam], params["system"])
    assert [block["text"] for block in system] == parts
    assert all(block["cache_control"] == EPHEMERAL for block in system)
    assert _count_cache_markers(params) == len(parts) + 1 <= 4
    assert NEVER_SENT.isdisjoint(params)
    assert ("betas" in params) is ("fallbacks" in params) is fallback
    assert ("tools" in params) is (n_tools > 0)
    assert params["messages"] == [USER]
    assert params["max_tokens"] == MAX_TOKENS_BY_EFFORT[effort]


# ══ A1 step 3: failures → LLMUnavailable / LLMBadRequest, and the logs ════════════════════


def _api_error(status: int, error_type: str | None, message: str = "details") -> httpx2.Response:
    body = {"type": "error", "error": {"type": error_type, "message": message}}
    return httpx2.Response(status, json=body, headers={"request-id": f"req_{status}"})


def _error_event(error_type: str) -> httpx2.Response:
    """A stream that opens fine (HTTP 200), then carries an `error` event."""
    first = next(sse_events(end_turn("x")))
    error = {"type": "error", "error": {"type": error_type, "message": "mid-stream"}}
    event = f"event: error\ndata: {json.dumps(error)}\n\n".encode()
    return httpx2.Response(200, headers=SSE_HEADERS, content=first + event)


REQUEST_ERRORS = [
    (400, "invalid_request_error"),
    (401, "authentication_error"),
    (403, "permission_error"),
    (404, "not_found_error"),
    (413, "request_too_large"),
    (422, "invalid_request_error"),
]
TRANSIENT_ERRORS = [
    (408, "timeout_error"),
    (409, "conflict_error"),
    (429, "rate_limit_error"),
    (500, "api_error"),
    (503, "api_error"),
    (504, "timeout_error"),
    (529, "overloaded_error"),
]


@pytest.mark.parametrize(("status", "error_type"), REQUEST_ERRORS)
async def test_a_rejected_request_is_a_bad_request_and_is_not_retried(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture, status: int, error_type: str
) -> None:
    api = _Api(_api_error(status, error_type, "messages.1: bad"))

    with (
        caplog.at_level(logging.WARNING, logger="app.agent.llm"),
        pytest.raises(LLMBadRequest) as raised,
    ):
        await make_llm(api).create(SYSTEM, [USER])

    assert (raised.value.status_code, raised.value.error_type) == (status, error_type)
    assert raised.value.request_id == f"req_{status}"
    # Review A1.3 R6: the API's free text can quote the request: kept only for a debugger.
    assert "messages.1: bad" not in str(raised.value)
    assert raised.value._api_message == "messages.1: bad"
    assert len(api.requests) == 1  # not retried
    assert [r.levelno for r in caplog.records] == [logging.ERROR]
    assert "messages.1: bad" not in caplog.text
    assert f"req_{status}" in caplog.text  # the request id finds the details in the Console


@pytest.mark.parametrize(("status", "error_type"), TRANSIENT_ERRORS)
async def test_a_transient_failure_is_unavailable(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture, status: int, error_type: str
) -> None:
    api = _Api(_api_error(status, error_type))

    with (
        caplog.at_level(logging.WARNING, logger="app.agent.llm"),
        pytest.raises(LLMUnavailable, match=f"HTTP {status}"),
    ):
        await make_llm(api, max_retries=0).create(SYSTEM, [USER])

    assert [r.levelno for r in caplog.records] == [logging.WARNING]


@pytest.mark.parametrize(
    "failure",
    [httpx2.ConnectError("refused"), httpx2.ReadTimeout("silence")],
    ids=["connection refused", "timeout before the stream"],
)
async def test_no_connection_is_unavailable(make_llm: MakeLLM, failure: Exception) -> None:
    def fail(request: httpx2.Request) -> httpx2.Response:
        raise failure

    api = _Api()
    api._handle = fail  # type: ignore[method-assign]

    with pytest.raises(LLMUnavailable, match="unreachable"):
        await make_llm(api, max_retries=0).create(SYSTEM, [USER])


async def test_an_overload_inside_the_stream_is_unavailable(make_llm: MakeLLM) -> None:
    # The stream opened with HTTP 200: only the event's error type says what failed.
    api = _Api(_error_event("overloaded_error"))

    with pytest.raises(LLMUnavailable, match="overloaded_error"):
        await make_llm(api).create(SYSTEM, [USER])

    assert len(api.requests) == 1


async def test_a_request_error_inside_the_stream_is_a_bad_request(make_llm: MakeLLM) -> None:
    api = _Api(_error_event("invalid_request_error"))

    with pytest.raises(LLMBadRequest) as raised:
        await make_llm(api).create(SYSTEM, [USER])

    assert raised.value.error_type == "invalid_request_error"


async def test_a_stream_that_ends_early_never_hands_out_half_a_message(
    make_llm: MakeLLM,
) -> None:
    # Without message_stop the SDK returns the partial snapshot (stop_reason None).
    events = list(sse_events(end_turn("Am văzut 500 lei la")))
    api = _Api(httpx2.Response(200, headers=SSE_HEADERS, content=b"".join(events[:3])))

    with pytest.raises(LLMUnavailable, match="ended before"):
        await make_llm(api).create(SYSTEM, [USER])


async def test_malformed_streamed_tool_input_is_unavailable(make_llm: MakeLLM) -> None:
    good = b"".join(sse_events(tool_round_one_call()))
    broken = good.replace(b'"partial_json": "{\\"n\\": 1}"', b'"partial_json": "{\\"n\\": oops"')
    assert broken != good
    api = _Api(httpx2.Response(200, headers=SSE_HEADERS, content=broken))

    with pytest.raises(LLMUnavailable, match="stream couldn't be used"):
        await make_llm(api).create(SYSTEM, [USER])


@pytest.mark.parametrize(
    "response",
    [
        httpx2.Response(
            200, headers=SSE_HEADERS, content=b"".join(list(sse_events(end_turn("x")))[1:])
        ),
        httpx2.Response(200, json=wire(end_turn("x"))),
        httpx2.Response(200, headers=SSE_HEADERS, content=b""),
    ],
    ids=["no message_start", "a JSON body instead of a stream", "an empty stream"],
)
async def test_a_malformed_stream_is_unavailable(
    make_llm: MakeLLM, response: httpx2.Response
) -> None:
    # The SDK signals these with a bare `assert` / RuntimeError inside its stream helper.
    with pytest.raises(LLMUnavailable, match="stream couldn't be used"):
        await make_llm(_Api(response), max_retries=0).create(SYSTEM, [USER])


def tool_round_one_call() -> BetaMessage:
    return message(tool_use("get_plan_status", {"n": 1}, tool_use_id="t1"), stop_reason="tool_use")


async def test_the_sdk_retries_twice_before_giving_up(make_llm: MakeLLM) -> None:
    overloaded = [_api_error(529, "overloaded_error") for _ in range(3)]
    for response in overloaded:
        response.headers["retry-after-ms"] = "1"  # the SDK honours it: no real backoff in tests
    api = _Api(*overloaded)

    with pytest.raises(LLMUnavailable):
        await make_llm(api).create(SYSTEM, [USER])

    assert len(api.requests) == 3  # max_retries=2 really reaches the SDK


async def test_a_retry_that_succeeds_returns_the_answer(make_llm: MakeLLM) -> None:
    first, second = _api_error(529, "overloaded_error"), _api_error(529, "overloaded_error")
    first.headers["retry-after-ms"] = second.headers["retry-after-ms"] = "1"
    api = _Api(first, second, end_turn("Am revenit."))

    reply = await make_llm(api).create(SYSTEM, [USER])

    assert len(api.requests) == 3
    assert reply.stop_reason == "end_turn"


async def test_cancelling_the_call_is_not_turned_into_unavailable() -> None:
    # A7's 5 s template relies on cancellation (asyncio.timeout) reaching the caller unchanged.
    started = asyncio.Event()

    async def never_answer(request: httpx2.Request) -> httpx2.Response:
        started.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable")

    llm = LLM(
        api_key=KEY,
        model=MODEL,
        effort="low",
        refusal_fallback=False,
        http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(never_answer)),
    )
    call = asyncio.create_task(llm.create(SYSTEM, [USER]))
    await started.wait()
    call.cancel()

    with pytest.raises(asyncio.CancelledError):
        await call
    await llm.aclose()


@pytest.mark.parametrize(
    ("status", "expected"),
    [(428, LLMBadRequest), (429, LLMUnavailable), (499, LLMBadRequest), (500, LLMUnavailable)],
)
def test_the_edges_of_the_status_rules(status: int, expected: type[LLMError]) -> None:
    assert classify(status, None) is expected


async def test_an_html_error_page_is_still_classified_by_status(make_llm: MakeLLM) -> None:
    html = httpx2.Response(502, headers={"content-type": "text/html"}, content=b"<html>502</html>")

    with pytest.raises(LLMUnavailable, match="HTTP 502"):
        await make_llm(_Api(html), max_retries=0).create(SYSTEM, [USER])


async def test_a_bad_request_without_a_body_has_no_error_type(make_llm: MakeLLM) -> None:
    with pytest.raises(LLMBadRequest) as raised:
        await make_llm(_Api(httpx2.Response(400, content=b""))).create(SYSTEM, [USER])

    assert raised.value.error_type is None
    assert raised.value.status_code == 400


# ── security: the key and the user's words stay out of errors and logs ──────────────────


async def test_the_key_never_appears_in_errors_tracebacks_or_any_log(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)  # every logger, the SDK's included
    failures: list[httpx2.Response] = [
        _api_error(400, "invalid_request_error"),
        _api_error(401, "authentication_error"),
        _api_error(529, "overloaded_error"),
        _error_event("overloaded_error"),
    ]
    raised: list[LLMError] = []
    for failure in failures:
        with pytest.raises(LLMError) as caught:
            await make_llm(_Api(failure), max_retries=0).create(SYSTEM, [USER])
        raised.append(caught.value)

    for error in raised:
        assert KEY not in str(error)
        assert KEY not in repr(error)
        assert KEY not in "".join(traceback.format_exception(error))  # the chained SDK error too
    assert KEY not in caplog.text


async def test_our_logs_never_contain_what_the_user_or_claude_said(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    private: BetaMessageParam = {"role": "user", "content": "PRIVATE-USER-TEXT 500 lei"}
    refused = message(
        text("PRIVATE-PARTIAL-REPLY"), stop_reason="refusal", refusal_category="general_harms"
    )
    api = _Api(end_turn("PRIVATE-REPLY"), refused, _api_error(400, "invalid_request_error"))
    llm = make_llm(api)

    with caplog.at_level(logging.DEBUG, logger="app.agent.llm"):
        await llm.create(SYSTEM, [private])
        await llm.create(SYSTEM, [private])
        with pytest.raises(LLMBadRequest):
            await llm.create(SYSTEM, [private])

    ours = " ".join(r.getMessage() for r in caplog.records if r.name == "app.agent.llm")
    assert ours  # something was logged
    assert "PRIVATE" not in ours


# ── the logs that help (arch 6.8 caching, R5 refusals) ──────────────────────────────────


async def test_a_successful_call_logs_its_usage_once(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture
) -> None:
    reply = message(text("ok"), input_tokens=40, output_tokens=7, cache_read=1200, cache_write=300)

    with caplog.at_level(logging.INFO, logger="app.agent.llm"):
        await make_llm(_Api(reply)).create(SYSTEM, [USER])

    records = [r for r in caplog.records if r.name == "app.agent.llm"]
    assert [r.levelno for r in records] == [logging.INFO]
    line = records[0].getMessage()
    for part in (
        "model=claude-sonnet-5-5",
        "stop_reason=end_turn",
        "input_tokens=40",
        "output_tokens=7",
        "cache_read=1200",
        "cache_write=300",
    ):
        assert part in line


@pytest.mark.parametrize("fallback", [False, True], ids=["fallback off", "fallback on"])
async def test_a_refusal_is_logged_as_a_warning_with_its_category(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture, fallback: bool
) -> None:
    # Review R5: a refusal the fallback didn't rescue must be visible, without the content.
    refused = message(stop_reason="refusal", output_tokens=0, refusal_category="general_harms")

    with caplog.at_level(logging.INFO, logger="app.agent.llm"):
        got = await make_llm(_Api(refused), refusal_fallback=fallback).create(SYSTEM, [USER])

    assert got.stop_reason == "refusal"  # handed to the caller: A6 answers with its template
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "category=general_harms" in warnings[0]
    assert "model=claude-sonnet-5-5" in warnings[0]
    assert f"refusal_fallback={'on' if fallback else 'off'}" in warnings[0]


# ── idempotency, invariants, regression ─────────────────────────────────────────────────


async def test_a_failure_leaves_the_client_usable(make_llm: MakeLLM) -> None:
    api = _Api(_api_error(529, "overloaded_error"), end_turn("Am revenit."))
    llm = make_llm(api, max_retries=0)

    with pytest.raises(LLMUnavailable):
        await llm.create(SYSTEM, [USER])
    reply = await llm.create(SYSTEM, [USER])

    assert reply.stop_reason == "end_turn"


ERROR_TYPES = [
    None,
    "invalid_request_error",
    "authentication_error",
    "billing_error",
    "permission_error",
    "not_found_error",
    "request_too_large",
    "rate_limit_error",
    "api_error",
    "overloaded_error",
    "timeout_error",
    "some_future_error",
]
REQUEST_ERROR_TYPES = {
    "invalid_request_error",
    "authentication_error",
    "billing_error",
    "permission_error",
    "not_found_error",
    "request_too_large",
}


@given(status=st.integers(min_value=400, max_value=599), error_type=st.sampled_from(ERROR_TYPES))
def test_every_http_error_status_maps_by_status(status: int, error_type: str | None) -> None:
    transient = status in (408, 409, 429) or status >= 500
    assert classify(status, error_type) is (LLMUnavailable if transient else LLMBadRequest)


@given(error_type=st.sampled_from(ERROR_TYPES))
def test_an_error_inside_a_stream_maps_by_its_type(error_type: str | None) -> None:
    # HTTP 200: the request was accepted, so only a request-error type means "our bug".
    expected = LLMBadRequest if error_type in REQUEST_ERROR_TYPES else LLMUnavailable
    assert classify(200, error_type) is expected


def test_effort_is_defined_once_in_app_config() -> None:
    # Review R6: the agent imports the settings' Effort instead of keeping its own copy.
    assert "Effort = Literal" not in inspect.getsource(app.agent.llm)
    assert set(typing.get_args(Effort)) == {"low", "medium", "high", "xhigh", "max"}


# ══ Review of A1.3 ═════════════════════════════════════════════════════════════════════════

PRIVATE = "PRIVATE"  # a marker for anything the user or Claude said


def _tool_call_stream(*chunks: str) -> httpx2.Response:
    """A `record_expense` tool call whose input arrives as these `input_json_delta` chunks."""
    shell = message(tool_use("record_expense", {}, tool_use_id="toolu_m"), stop_reason="tool_use")
    start, block_start, _delta, *rest = sse_events(shell)
    deltas = [
        sse(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": chunk},
            }
        )
        for chunk in chunks
    ]
    return httpx2.Response(
        200, headers=SSE_HEADERS, content=start + block_start + b"".join(deltas) + b"".join(rest)
    )


# ── R8: a tool input is used only if it is complete, strict JSON (money-critical) ───────


@pytest.mark.parametrize(
    "chunks",
    [
        ['{"amount": 50'],  # cut inside a number: the lenient parse would say 50, not 500
        ['{"amount": 500'],  # cut before the closing brace
        ['{"amount": 500, "note": "PRIVATE" oops'],  # trailing garbage
        ['{"amount": 500} {"amount": 5}'],  # two objects
        ['{"amount": NaN}'],  # not JSON
        ['{"amount": Infinity}'],
        ["[500]"],  # JSON, but not an object
    ],
    ids=[
        "truncated number",
        "truncated object",
        "trailing garbage",
        "two objects",
        "NaN",
        "Infinity",
        "not an object",
    ],
)
async def test_a_tool_call_with_an_incomplete_or_lenient_input_is_never_returned(
    make_llm: MakeLLM, chunks: list[str]
) -> None:
    with pytest.raises(LLMUnavailable, match="stream couldn't be used") as raised:
        await make_llm(_Api(_tool_call_stream(*chunks))).create(SYSTEM, [USER])

    assert PRIVATE not in str(raised.value)


async def test_a_tool_input_split_over_many_chunks_is_put_back_together(
    make_llm: MakeLLM,
) -> None:
    chunks = ['{"amo', 'unt": 5', '00, "note": "căști', ' 🎧"}']

    reply = await make_llm(_Api(_tool_call_stream(*chunks))).create(SYSTEM, [USER])

    call = reply.content[0]
    assert call.type == "tool_use"
    assert call.input == {"amount": 500, "note": "căști 🎧"}


async def test_a_tool_call_without_input_deltas_keeps_its_empty_input(make_llm: MakeLLM) -> None:
    reply = await make_llm(_Api(_tool_call_stream())).create(SYSTEM, [USER])

    call = reply.content[0]
    assert call.type == "tool_use"
    assert call.input == {}


async def test_tool_json_for_a_text_block_is_a_corrupt_stream(make_llm: MakeLLM) -> None:
    # The SDK silently ignores an input_json_delta aimed at a text block; we don't.
    start, *rest = sse_events(end_turn("ok"))
    stray = sse(
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": '{"amount": 500}'},
        }
    )
    body = start + rest[0] + stray + b"".join(rest[1:])
    api = _Api(httpx2.Response(200, headers=SSE_HEADERS, content=body))

    with pytest.raises(LLMUnavailable, match="isn't a tool call"):
        await make_llm(api).create(SYSTEM, [USER])


# ── R4, R5: only a complete stream is a message ─────────────────────────────────────────


async def test_a_stream_cut_after_message_delta_is_not_complete(make_llm: MakeLLM) -> None:
    # message_delta carries the stop reason, but without message_stop the stream was cut.
    events = list(sse_events(end_turn("Am văzut")))
    api = _Api(httpx2.Response(200, headers=SSE_HEADERS, content=b"".join(events[:-1])))

    with pytest.raises(LLMUnavailable, match="ended before message_stop"):
        await make_llm(api).create(SYSTEM, [USER])


async def test_a_missing_final_message_is_caught_even_without_the_sdks_assert(
    make_llm: MakeLLM, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Under `python -O` the SDK's own `assert` is gone and get_final_message() returns None.
    from anthropic.lib.streaming._beta_messages import BetaAsyncMessageStream

    async def none(self: object) -> None:
        return None

    monkeypatch.setattr(BetaAsyncMessageStream, "get_final_message", none)

    # The explicit guard, not an AttributeError caught by the catch-all.
    with pytest.raises(LLMUnavailable, match="ended before the message was complete"):
        await make_llm(_Api(end_turn("ok"))).create(SYSTEM, [USER])


@pytest.mark.slow
def test_an_empty_stream_is_unavailable_under_python_O() -> None:
    script = """
import asyncio, httpx2
from app.agent.llm import LLM, LLMUnavailable
async def main():
    empty = httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=b"")
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(lambda request: empty))
    llm = LLM(api_key="k", model="m", effort="low", refusal_fallback=False, max_retries=0,
              http_client=client)
    try:
        await llm.create(["rules"], [{"role": "user", "content": "hi"}])
    except LLMUnavailable:
        print("LLMUnavailable")
    finally:
        await llm.aclose()
asyncio.run(main())
"""
    backend = Path(__file__).resolve().parents[2]
    done = subprocess.run(  # noqa: S603 - our own interpreter, a fixed script
        [sys.executable, "-O", "-c", script],
        cwd=backend,
        env={**os.environ, "PYTHONPATH": str(backend), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert done.stdout.strip() == "LLMUnavailable", done.stderr[-500:]


# ── R2: whatever the SDK raises while reading a malformed stream is "unavailable" ───────


def _malformed(reply: BetaMessage, old: bytes, new: bytes) -> httpx2.Response:
    body = b"".join(sse_events(reply))
    assert old in body
    return httpx2.Response(200, headers=SSE_HEADERS, content=body.replace(old, new, 1))


@pytest.mark.parametrize(
    "response",
    [
        _malformed(end_turn("PRIVATE"), b'"index": 0, "delta"', b'"index": 5, "delta"'),
        _malformed(
            end_turn("PRIVATE"), b'"type": "text_delta", "text"', b'"type": "text_delta", "t"'
        ),
        httpx2.Response(
            200,
            headers=SSE_HEADERS,
            content=next(sse_events(end_turn("x")))
            + sse(
                {
                    "type": "content_block_start",
                    "index": 0,
                    "content_block": {"type": "fallback", "from": {"model": "claude-sonnet-5-5"}},
                }
            ),
        ),
        httpx2.Response(
            200,
            headers=SSE_HEADERS,
            content=next(sse_events(end_turn("x")))
            + b"event: content_block_start\ndata: {not json PRIVATE\n\n",
        ),
    ],
    ids=["delta for a missing block", "text_delta without text", "fallback without to", "bad JSON"],
)
async def test_a_stream_the_sdk_cannot_read_is_unavailable(
    make_llm: MakeLLM, response: httpx2.Response
) -> None:
    # IndexError, TypeError, AttributeError, JSONDecodeError… from inside the SDK.
    with pytest.raises(LLMUnavailable, match="stream couldn't be used"):
        await make_llm(_Api(response)).create(SYSTEM, [USER])


# ── R3: a request that isn't strict JSON is our bug, reported before anything is sent ───


def _with_tool_input(value: object) -> list[BetaMessageParam]:
    call = {"type": "tool_use", "id": "toolu_1", "name": "record_expense", "input": {"a": value}}
    result = {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}
    return cast(
        list[BetaMessageParam],
        [USER, {"role": "assistant", "content": [call]}, {"role": "user", "content": [result]}],
    )


@pytest.mark.parametrize(
    ("value", "error"),
    [
        (float("nan"), ValueError),
        (float("inf"), ValueError),
        (Decimal("1.5"), TypeError),
        (date(2026, 6, 15), TypeError),
        (b"\xff", TypeError),
        ({1, 2}, TypeError),
    ],
    ids=["NaN", "Infinity", "Decimal", "date", "bytes", "set"],
)
async def test_a_request_that_is_not_strict_json_is_rejected_before_anything_is_sent(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture, value: object, error: type[Exception]
) -> None:
    api = _Api(end_turn("ok"))

    with caplog.at_level(logging.WARNING, logger="app.agent.llm"), pytest.raises(error) as raised:
        await make_llm(api).create(SYSTEM, _with_tool_input(value))

    assert api.requests == []
    assert "messages[1].content[0].input.a" in str(raised.value)  # says where
    assert caplog.records == []  # a programming error, not "Claude is unavailable"


async def test_a_non_string_key_is_rejected_before_anything_is_sent(make_llm: MakeLLM) -> None:
    api = _Api(end_turn("ok"))
    messages = _with_tool_input("ok")
    cast(dict[Any, Any], cast(list[Any], messages[1]["content"])[0]["input"])[7] = "x"

    with pytest.raises(TypeError, match="key"):
        await make_llm(api).create(SYSTEM, messages)

    assert api.requests == []


# ── R1, R6, R9: no content from the request or the response in any error ──────────────


def _leaky_failures() -> list[httpx2.Response]:
    private_body = {"type": "error", "error": {"type": "invalid_request_error", "message": PRIVATE}}
    return [
        httpx2.Response(400, json=private_body),
        httpx2.Response(529, json={**private_body, "error": {"type": "overloaded_error"}}),
        httpx2.Response(502, headers={"content-type": "text/html"}, content=PRIVATE.encode()),
        _error_event_with(PRIVATE),
        _tool_call_stream('{"note": "PRIVATE" oops'),
        _malformed(end_turn("PRIVATE"), b'"index": 0, "delta"', b'"index": 5, "delta"'),
        httpx2.Response(
            200, headers=SSE_HEADERS, content=b"".join(list(sse_events(end_turn(PRIVATE)))[:-1])
        ),
    ]


def _error_event_with(text: str) -> httpx2.Response:
    first = next(sse_events(end_turn("x")))
    error = {"type": "error", "error": {"type": "invalid_request_error", "message": text}}
    return httpx2.Response(200, headers=SSE_HEADERS, content=first + sse(error))


@pytest.mark.parametrize(
    "index",
    range(7),
    ids=[
        "400 body",
        "529 body",
        "502 HTML",
        "error event",
        "bad tool JSON",
        "unreadable stream",
        "cut stream",
    ],
)
async def test_no_failure_carries_request_or_response_content(
    make_llm: MakeLLM, caplog: pytest.LogCaptureFixture, index: int
) -> None:
    private_user: BetaMessageParam = {"role": "user", "content": f"{PRIVATE} 500 lei"}
    api = _Api(_leaky_failures()[index])

    with caplog.at_level(logging.DEBUG, logger="app.agent.llm"), pytest.raises(LLMError) as raised:
        await make_llm(api, max_retries=0).create(SYSTEM, [private_user])

    error = raised.value
    assert PRIVATE not in str(error)
    assert PRIVATE not in repr(error)
    assert PRIVATE not in "".join(traceback.format_exception(error))
    # The SDK's exception (holding the response body or the tool JSON buffer) isn't attached.
    assert error.__cause__ is None
    assert error.__context__ is None
    ours = " ".join(r.getMessage() for r in caplog.records if r.name == "app.agent.llm")
    assert PRIVATE not in ours


async def test_an_unavailable_error_keeps_only_safe_metadata(make_llm: MakeLLM) -> None:
    response = _api_error(529, "overloaded_error", PRIVATE)

    with pytest.raises(LLMUnavailable) as raised:
        await make_llm(_Api(response), max_retries=0).create(SYSTEM, [USER])

    error = raised.value
    assert (error.status_code, error.error_type, error.request_id) == (
        529,
        "overloaded_error",
        "req_529",
    )


# ── R7: a missing key is said once, loudly, not on every call ───────────────────────────


async def test_a_missing_key_is_logged_once_not_on_every_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.agent.llm"):
        llm = LLM(api_key=None, model=MODEL, effort="low", refusal_fallback=False)
        for _ in range(3):
            with pytest.raises(LLMUnavailable):
                await llm.create(SYSTEM, [USER])

    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "ANTHROPIC_API_KEY is not set" in warnings[0].getMessage()


# ══ A1 step 5: from_settings, get_llm / set_llm (happy paths) ═══════════════════════════


async def test_from_settings_uses_the_settings(settings: Settings) -> None:
    configured = settings.model_copy(
        update={
            "ANTHROPIC_API_KEY": SecretStr(KEY),
            "ANTHROPIC_MODEL": "claude-opus-5-5",
            "ANTHROPIC_EFFORT": "medium",
            "ANTHROPIC_REFUSAL_FALLBACK": True,
        }
    )
    api = _Api(end_turn("ok"))
    llm = LLM.from_settings(configured, http_client=api.http_client())
    try:
        await llm.create(SYSTEM, [USER])
    finally:
        await llm.aclose()

    body, headers = api.body(), api.requests[0].headers
    assert (body["model"], body["output_config"], body["fallbacks"]) == (
        "claude-opus-5-5",
        {"effort": "medium"},
        "default",
    )
    assert headers["authorization"] == f"Bearer {KEY}"


async def test_from_settings_without_a_key_is_unavailable(settings: Settings) -> None:
    llm = LLM.from_settings(settings)  # the defaults: no key

    with pytest.raises(LLMUnavailable, match="ANTHROPIC_API_KEY is not set"):
        await llm.create(SYSTEM, [USER])


@pytest.fixture
def no_process_llm() -> Iterator[None]:
    set_llm(None)
    yield
    set_llm(None)


@pytest.mark.usefixtures("no_process_llm")
def test_get_llm_builds_one_client_and_set_llm_swaps_it() -> None:
    first = get_llm()
    assert isinstance(first, LLM)
    assert get_llm() is first  # one client per process

    fake = FakeLLM([])
    set_llm(fake)
    assert get_llm() is fake

    set_llm(None)
    assert get_llm() is not first  # rebuilt from the settings
