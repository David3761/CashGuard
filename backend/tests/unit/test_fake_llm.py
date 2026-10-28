"""A1 step 1: the LLM error types, `check_system`, `FakeLLM` and its response builders.

`FakeLLM` stands in for `app.agent.llm.LLM` in every non-live test (how-we-work §7), so A6's loop
tests are only as good as this fake: it must return real SDK objects, in order, record exactly
what was sent, and fail loudly when a test scripts too few responses.
"""

import asyncio
import collections.abc
import contextlib
import copy
import typing
from typing import cast

import pytest
from anthropic.types.beta import (
    BetaMessage,
    BetaMessageParam,
    BetaRefusalStopDetails,
    BetaToolParam,
)
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.agent.llm import (
    MAX_SYSTEM_PARTS,
    LLMBadRequest,
    LLMClient,
    LLMError,
    LLMUnavailable,
    check_system,
)
from tests.fakes.fake_llm import (
    FakeLLM,
    RecordedRequest,
    RefusalCategory,
    ScriptExhausted,
    cut_off,
    end_turn,
    message,
    redacted_thinking,
    refusal,
    text,
    thinking,
    tool_round,
    tool_use,
)

SYSTEM = ["Reguli fixe (RO + EN).", "Snapshot: Matei, luni 15 iunie 2026."]
USER: BetaMessageParam = {"role": "user", "content": "Am luat ceva de la Mega Image."}
TOOL: BetaToolParam = {
    "name": "get_plan_status",
    "description": "Read the current plan. Use it when the user asks how they're doing.",
    "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    "strict": True,
}

# What the API sends for a tool call (arch 6.1), with the Sonnet 5.5 thinking block (empty text
# under the default `display: "omitted"`) and the usage fields arch 6.8 reads. The builders must
# produce exactly this shape, so a test can't script something the real API never sends.
DOCUMENTED_TOOL_USE_RESPONSE = {
    "id": "msg_fake",
    "type": "message",
    "role": "assistant",
    "model": "claude-sonnet-5-5",
    "content": [
        {"type": "thinking", "thinking": "", "signature": "sig-fake"},
        {
            "type": "tool_use",
            "id": "toolu_01A",
            "name": "add_life_event",
            "input": {"name": "Concert", "date": "2026-11-05", "est_cost": 100, "type": "social"},
        },
    ],
    "stop_reason": "tool_use",
    "stop_sequence": None,
    "stop_details": None,
    "usage": {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    },
}


def _ping(tool_use_id: str) -> BetaMessage:
    return tool_round(tool_use("get_plan_status", {}, tool_use_id=tool_use_id))


# ── happy path ───────────────────────────────────────────────────────────────────────────


async def test_fake_returns_the_scripted_response_and_records_the_request() -> None:
    reply = end_turn("Bună! Partea ta a fost 100 lei.")
    fake = FakeLLM([reply])

    got = await fake.create(SYSTEM, [USER], [TOOL])

    assert got is reply
    assert fake.requests == [RecordedRequest(system=tuple(SYSTEM), messages=[USER], tools=[TOOL])]
    assert fake.requests[0].tool_names == ["get_plan_status"]


async def test_fake_returns_responses_in_script_order() -> None:
    script = [_ping("toolu_1"), _ping("toolu_2"), end_turn("Gata.")]
    fake = FakeLLM(script)

    got = [await fake.create(SYSTEM, [USER]) for _ in script]

    assert all(g is s for g, s in zip(got, script, strict=True))
    assert fake.remaining == 0
    assert fake.requests[0].tools == []


def test_builders_produce_api_shaped_blocks_and_usage() -> None:
    built = message(
        thinking(),
        redacted_thinking("opaque"),
        text("Mă uit la plan."),
        tool_use(
            "annotate_transaction", {"transaction_id": 918, "people_count": 5}, tool_use_id="a"
        ),
        tool_use("create_receivable", {"transaction_id": 918}, tool_use_id="b"),
        stop_reason="tool_use",
        cache_read=1200,
        cache_write=300,
    )

    assert isinstance(built, BetaMessage)
    assert [b.type for b in built.content] == [
        "thinking",
        "redacted_thinking",
        "text",
        "tool_use",
        "tool_use",
    ]
    first, second, _, call_a, call_b = built.content
    assert first.type == "thinking"
    assert (first.thinking, first.signature) == ("", "sig-fake")
    assert second.type == "redacted_thinking"
    assert second.data == "opaque"
    assert call_a.type == "tool_use"
    assert call_b.type == "tool_use"
    assert (call_a.id, call_a.name, call_a.input) == (
        "a",
        "annotate_transaction",
        {"transaction_id": 918, "people_count": 5},
    )
    assert call_b.id == "b"
    assert built.stop_reason == "tool_use"
    assert built.stop_details is None
    assert built.usage.cache_read_input_tokens == 1200
    assert built.usage.cache_creation_input_tokens == 300


def test_refusal_and_cut_off_builders() -> None:
    refused = refusal("general_harms")
    cut = cut_off("Am văzut 500 lei la")

    assert refused.content == []
    assert refused.stop_reason == "refusal"
    assert refused.stop_details is not None
    assert refused.stop_details.category == "general_harms"
    assert refusal(None).stop_details is not None  # the API may send a refusal with no category
    assert cut.stop_reason == "max_tokens"
    assert [b.type for b in cut.content] == ["text"]


# ── boundaries ───────────────────────────────────────────────────────────────────────────


async def test_empty_script_raises_script_exhausted_on_the_first_call() -> None:
    fake = FakeLLM([])

    with pytest.raises(ScriptExhausted, match=r"request 1 .* 0 response"):
        await fake.create(SYSTEM, [USER])

    assert len(fake.requests) == 1  # the request that overran is still recorded


async def test_call_after_the_last_scripted_response_raises_script_exhausted() -> None:
    fake = FakeLLM([end_turn("unu"), end_turn("doi")])
    await fake.create(SYSTEM, [USER])
    await fake.create(SYSTEM, [USER])

    with pytest.raises(ScriptExhausted, match=r"request 3 .* 2 response"):
        await fake.create(SYSTEM, [USER])


async def test_assert_consumed_fails_while_responses_are_left() -> None:
    fake = FakeLLM([end_turn("unu"), end_turn("doi")])
    await fake.create(SYSTEM, [USER])

    with pytest.raises(AssertionError, match="1 scripted response"):
        fake.assert_consumed()

    await fake.create(SYSTEM, [USER])
    fake.assert_consumed()


async def test_assert_consumed_fails_after_an_overrun_even_if_it_was_swallowed() -> None:
    # Only an `except BaseException` can swallow ScriptExhausted; the final check still catches it.
    fake = FakeLLM([])
    with contextlib.suppress(BaseException):  # deliberately swallowed
        await fake.create(SYSTEM, [USER])

    with pytest.raises(AssertionError, match="exhausted"):
        fake.assert_consumed()


@pytest.mark.parametrize("parts", [["only rules"], ["rules", "trigger", "snapshot"]])
async def test_fake_accepts_one_to_three_system_parts(parts: list[str]) -> None:
    fake = FakeLLM([end_turn("ok")])

    await fake.create(parts, [USER])

    assert fake.requests[0].system == tuple(parts)
    assert len(parts) <= MAX_SYSTEM_PARTS


@pytest.mark.parametrize("parts", [[], ["a", "b", "c", "d"]])
async def test_fake_rejects_zero_or_more_than_three_system_parts(parts: list[str]) -> None:
    fake = FakeLLM([end_turn("ok")])

    with pytest.raises(ValueError, match="1 to 3 parts"):
        await fake.create(parts, [USER])

    assert fake.requests == []  # like the real LLM: nothing is sent
    assert fake.remaining == 1


# ── invalid input ────────────────────────────────────────────────────────────────────────


def test_check_system_returns_the_parts_as_a_tuple() -> None:
    assert check_system(["rules", "snapshot"]) == ("rules", "snapshot")


def test_check_system_rejects_a_bare_string() -> None:
    # A str is a Sequence[str] too: it would silently become one system part per character.
    with pytest.raises(TypeError, match="not a single str"):
        check_system("rules")


@pytest.mark.parametrize("blank", ["", "  \n\t"])
def test_check_system_rejects_blank_parts(blank: str) -> None:
    with pytest.raises(ValueError, match="part 1 is empty"):
        check_system(["rules", blank])


async def test_fake_applies_the_same_system_check() -> None:
    fake = FakeLLM([end_turn("ok")])

    with pytest.raises(TypeError, match="not a single str"):
        await fake.create("rules", [USER])


@pytest.mark.parametrize("bad", [None, {"type": "text", "text": "rules"}, 7])
def test_check_system_names_a_part_that_is_not_a_str(bad: object) -> None:
    with pytest.raises(TypeError, match=r"system part 1 must be a str, got (NoneType|dict|int)"):
        check_system(cast(list[str], ["rules", bad]))


@pytest.mark.parametrize(
    ("blocks", "stop_reason"),
    [
        ([tool_use("get_plan_status", {}, tool_use_id="a")], "end_turn"),
        ([tool_use("get_plan_status", {}, tool_use_id="a")], "stop_sequence"),
        ([text("no call")], "tool_use"),
        ([], "tool_use"),
    ],
)
def test_message_rejects_a_stop_reason_that_contradicts_the_content(
    blocks: list[dict[str, object]], stop_reason: typing.Any
) -> None:
    # The API stops with "tool_use" whenever it emits a tool call, and only then (review #1).
    with pytest.raises(ValueError, match="stop_reason"):
        message(*blocks, stop_reason=stop_reason)


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_message_allows_partial_output_on_refusal_and_max_tokens(stop_reason: typing.Any) -> None:
    # A decline or a cut-off can leave partial output; A6 must discard it, so tests need it.
    partial = message(
        text("Am văzut"), tool_use("get_plan_status", {}, tool_use_id="a"), stop_reason=stop_reason
    )

    assert partial.stop_reason == stop_reason


def test_message_rejects_duplicate_tool_use_ids() -> None:
    with pytest.raises(ValueError, match="duplicate tool_use id 'a'"):
        tool_round(tool_use("x", {}, tool_use_id="a"), tool_use("y", {}, tool_use_id="a"))


def test_script_rejects_a_tool_use_id_used_in_two_responses() -> None:
    with pytest.raises(ValueError, match="'toolu_1' appears in two"):
        FakeLLM(
            [
                _ping("toolu_1"),
                tool_round(tool_use("get_plan_status", {}, tool_use_id="toolu_1"), msg_id="other"),
            ]
        )


def test_script_rejects_two_responses_with_the_same_id() -> None:
    with pytest.raises(ValueError, match=r"share id .* pass msg_id"):
        FakeLLM([end_turn("ok"), end_turn("ok")])


def test_refusal_category_only_goes_with_a_refusal() -> None:
    with pytest.raises(ValueError, match="refusal_category"):
        message(text("x"), refusal_category="bio")


def test_builder_rejects_a_block_the_api_never_sends() -> None:
    with pytest.raises(ValidationError):
        message({"type": "bogus"})


def test_tool_round_needs_at_least_one_tool_use() -> None:
    with pytest.raises(ValueError, match="tool_use"):
        tool_round(thinking(), text("no call here"))


def test_script_items_must_be_messages_or_exceptions() -> None:
    with pytest.raises(TypeError, match="str"):
        FakeLLM([end_turn("ok"), "not a response"])  # type: ignore[list-item]


# ── error paths ──────────────────────────────────────────────────────────────────────────


async def test_scripted_error_is_raised_on_its_turn_and_the_script_continues() -> None:
    down = LLMUnavailable("overloaded")
    fake = FakeLLM([down, end_turn("Am revenit.")])

    with pytest.raises(LLMUnavailable) as raised:
        await fake.create(SYSTEM, [USER])
    reply = await fake.create(SYSTEM, [USER])

    assert raised.value is down
    assert len(fake.requests) == 2  # the failed call was recorded too
    assert reply.content[0].type == "text"


async def test_script_exhausted_is_not_swallowed_by_a_broad_except() -> None:
    fake = FakeLLM([])

    async def careless_caller() -> str:
        try:
            await fake.create(SYSTEM, [USER])
        except Exception:  # what an agent's "LLM failed → template" path looks like
            return "template"
        return "reply"

    with pytest.raises(ScriptExhausted):
        await careless_caller()


def test_error_hierarchy() -> None:
    assert issubclass(LLMUnavailable, LLMError)
    assert issubclass(LLMBadRequest, LLMError)
    # A mis-scripted test must fail loudly: not an LLMError, and not even an Exception, so the
    # agent's `except Exception` → template path can't swallow it (review A1.1 #4).
    assert issubclass(ScriptExhausted, BaseException)
    assert not issubclass(ScriptExhausted, Exception)


def test_bad_request_keeps_the_api_details() -> None:
    err = LLMBadRequest(
        "messages.1: bad", status_code=400, error_type="invalid_request_error", request_id="req_1"
    )
    bare = LLMBadRequest("no details")

    assert str(err) == "messages.1: bad"
    assert (err.status_code, err.error_type, err.request_id) == (
        400,
        "invalid_request_error",
        "req_1",
    )
    assert (bare.status_code, bare.error_type, bare.request_id) == (None, None, None)


# ── concurrency ──────────────────────────────────────────────────────────────────────────


async def test_create_yields_to_the_event_loop_like_a_network_call() -> None:
    # A fake that never yields hides interleavings the real client has (review A1.1 #5).
    fake = FakeLLM([end_turn("ok")])
    order: list[str] = []

    async def call() -> None:
        await fake.create(SYSTEM, [USER])
        order.append("create returned")

    async def other() -> None:
        order.append("other task ran")

    await asyncio.gather(call(), other())

    assert order == ["other task ran", "create returned"]


async def test_concurrent_calls_get_the_response_scripted_for_their_turn() -> None:
    script = [end_turn("unu"), end_turn("doi"), end_turn("trei")]
    fake = FakeLLM(script)
    users: list[BetaMessageParam] = [{"role": "user", "content": f"mesaj {i}"} for i in range(3)]

    got = await asyncio.gather(*(fake.create(SYSTEM, [user]) for user in users))

    assert all(g is s for g, s in zip(got, script, strict=True))
    assert [r.messages for r in fake.requests] == [[user] for user in users]


# ── idempotency (recording is a snapshot) ────────────────────────────────────────────────


async def test_recorded_request_is_a_snapshot_the_caller_cannot_change() -> None:
    # A6 appends the assistant turn and the tool results to its own list after each call.
    first = _ping("toolu_1")
    fake = FakeLLM([first, end_turn("Gata.")])
    messages: list[BetaMessageParam] = [USER]
    system = list(SYSTEM)
    tools = [TOOL]

    await fake.create(system, messages, tools)
    messages.append({"role": "assistant", "content": first.content})
    system.append("later")
    tools.clear()

    assert fake.requests[0].messages == [USER]
    assert fake.requests[0].system == tuple(SYSTEM)
    assert fake.requests[0].tools == [TOOL]


async def test_fake_does_not_mutate_the_callers_inputs() -> None:
    messages: list[BetaMessageParam] = [USER]
    before = copy.deepcopy(messages)
    fake = FakeLLM([end_turn("ok")])

    await fake.create(SYSTEM, messages, [TOOL])

    assert messages == before


async def test_built_messages_own_their_data() -> None:
    # Nested values must not be shared with the test's data or between messages (review #8).
    args: dict[str, list[dict[str, object]]] = {"items": [{"name": "căști", "price": 199}]}
    block = tool_use("annotate_transaction", args, tool_use_id="a")
    first = tool_round(block, msg_id="first")
    args["items"].append({"name": "later"})
    second = tool_round(block, msg_id="second")
    first_call = first.content[0]
    second_call = second.content[0]
    assert first_call.type == "tool_use"
    assert second_call.type == "tool_use"
    first_items = first_call.input["items"]
    assert isinstance(first_items, list)
    first_items.clear()  # code under test mutating, in place, a response it got

    assert second_call.input == {"items": [{"name": "căști", "price": 199}]}
    assert block["input"] == {"items": [{"name": "căști", "price": 199}]}


def test_recorded_request_does_not_claim_to_be_hashable() -> None:
    # It holds lists of dicts: a frozen dataclass would promise a hash() that then raises.
    request = RecordedRequest(("rules",), [USER], [])

    assert not isinstance(request, collections.abc.Hashable)


# ── language ─────────────────────────────────────────────────────────────────────────────


async def test_romanian_text_and_emoji_are_recorded_unchanged() -> None:
    system = ["Răspunde în limba utilizatorului, fără judecăți.", "Ți-ai luat ceva de la eMAG?"]
    user: BetaMessageParam = {"role": "user", "content": "Și pentru colegi 🎧, cinci în total"}
    fake = FakeLLM([end_turn("Am înțeles: partea ta e 100 lei.")])

    reply = await fake.create(system, [user])

    assert fake.requests[0].system == tuple(system)
    assert fake.requests[0].messages == [user]
    assert reply.content[0].type == "text"
    assert reply.content[0].text == "Am înțeles: partea ta e 100 lei."


# ── invariants ───────────────────────────────────────────────────────────────────────────


@given(n=st.integers(min_value=0, max_value=15))
def test_any_script_is_served_in_order_then_exhausts(n: int) -> None:
    script = [end_turn(f"reply {i}") for i in range(n)]
    fake = FakeLLM(script)

    async def drive() -> list[BetaMessage]:
        served = [await fake.create(SYSTEM, [USER]) for _ in range(n)]
        with pytest.raises(ScriptExhausted):
            await fake.create(SYSTEM, [USER])
        return served

    served = asyncio.run(drive())

    assert all(g is s for g, s in zip(served, script, strict=True))
    assert len(fake.requests) == n + 1


# ── regression ───────────────────────────────────────────────────────────────────────────


def test_builder_output_has_exactly_the_documented_response_shape() -> None:
    built = tool_round(
        thinking(),
        tool_use(
            "add_life_event",
            {"name": "Concert", "date": "2026-11-05", "est_cost": 100, "type": "social"},
            tool_use_id="toolu_01A",
        ),
        msg_id="msg_fake",
    )

    assert built == BetaMessage.model_validate(DOCUMENTED_TOOL_USE_RESPONSE)
    assert built.model_dump(mode="json", exclude_unset=True) == DOCUMENTED_TOOL_USE_RESPONSE


def test_default_message_ids_are_deterministic_and_distinct() -> None:
    assert end_turn("a").id == end_turn("a").id
    assert end_turn("a").id != end_turn("b").id
    assert end_turn("a").id.startswith("msg_")


def test_refusal_categories_match_the_sdk() -> None:
    # RefusalCategory is copied from the SDK's inline Literal; this fails when the SDK changes it.
    optional = BetaRefusalStopDetails.model_fields["category"].annotation
    literal, none_type = typing.get_args(optional)

    assert none_type is type(None)
    assert set(typing.get_args(literal)) == set(typing.get_args(RefusalCategory))


def test_fake_llm_satisfies_the_llm_client_protocol() -> None:
    # The real check is static: mypy (in `make check`) verifies this assignment.
    llm: LLMClient = FakeLLM([])
    assert callable(llm.create)
