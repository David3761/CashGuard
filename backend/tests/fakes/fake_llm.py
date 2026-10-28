"""`FakeLLM`: the scripted stand-in for `app.agent.llm.LLM` in every non-live test (A1).

It returns the scripted responses in order, records a snapshot of every request, and fails
loudly when the script runs out. The builders return real, validated SDK objects
(`BetaMessage`) and reject shapes the API never sends (a `tool_use` stop without a call, repeated
ids…). It doesn't check the conversation itself yet (tool_result pairing, tools changed mid-run):
that's A1 step 4.

    script = [
        tool_round(thinking(), tool_use("get_plan_status", {}, tool_use_id="toolu_1")),
        end_turn("Ești pe drumul bun."),
    ]
    fake = FakeLLM(script)
    ...                                  # the code under test calls `await fake.create(...)`
    # the 2nd request carries the 1st response's content unchanged, then the tool result:
    assert fake.requests[1].messages[-2] == {"role": "assistant", "content": script[0].content}
    fake.assert_consumed()

Build scripts (and scripted exceptions) inside each test: the fake hands out the scripted objects
themselves, and an exception collects another traceback every time it's raised.
"""

import asyncio
import copy
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaStopReason, BetaToolParam

from app.agent.llm import check_system

Block = dict[str, Any]
# A copy of the SDK's inline Literal (BetaRefusalStopDetails.category); a test keeps them equal.
RefusalCategory = Literal["cyber", "bio", "frontier_llm", "reasoning_extraction", "general_harms"]


class FakeLLMFailure(BaseException):
    """A test bug the fake detected.

    A `BaseException`, like pytest's own `Failed`: the agent's `except Exception` → template
    fallback can't swallow it and turn a broken test green.
    """


class ScriptExhausted(FakeLLMFailure):
    """More calls than scripted responses."""


@dataclass
class RecordedRequest:
    """One call to `FakeLLM.create`, deep-copied when it was made. Not hashable: it holds lists."""

    system: tuple[str, ...]
    messages: list[BetaMessageParam]
    tools: list[BetaToolParam]

    @property
    def tool_names(self) -> list[str]:
        return [tool["name"] for tool in self.tools]


class FakeLLM:
    """Satisfies `app.agent.llm.LLMClient`. Script items are responses or exceptions to raise."""

    def __init__(self, script: Iterable[BetaMessage | Exception]) -> None:
        self._script = list(script)
        _check_script(self._script)
        self._next = 0
        self._overruns = 0
        self.requests: list[RecordedRequest] = []

    @property
    def remaining(self) -> int:
        return len(self._script) - self._next

    async def create(
        self,
        system: Sequence[str],
        messages: Sequence[BetaMessageParam],
        tools: Sequence[BetaToolParam] = (),
    ) -> BetaMessage:
        parts = check_system(system)  # same guard as the real LLM: nothing is "sent" if it fails
        # A snapshot: the caller (A6) keeps appending to its own lists after the call.
        self.requests.append(
            RecordedRequest(parts, copy.deepcopy(list(messages)), copy.deepcopy(list(tools)))
        )
        number = len(self.requests)
        item = self._script[self._next] if self.remaining else None  # the n-th call gets item n
        if item is None:
            self._overruns += 1
        else:
            self._next += 1
        await asyncio.sleep(0)  # yield like a network call, so concurrent callers interleave
        if item is None:
            raise ScriptExhausted(
                f"FakeLLM script exhausted: request {number} "
                f"but only {len(self._script)} response(s) scripted"
            )
        if isinstance(item, Exception):
            raise item
        return item

    def assert_consumed(self) -> None:
        """Fail unless every scripted response was used and no call overran the script."""
        if self._overruns:
            raise AssertionError(f"FakeLLM script exhausted {self._overruns} time(s)")
        if self.remaining:
            raise AssertionError(f"{self.remaining} scripted response(s) never requested")


def _check_script(script: list[BetaMessage | Exception]) -> None:
    """The real API never repeats a message id or a tool_use id."""
    message_ids: set[str] = set()
    call_ids: set[str] = set()
    for item in script:
        if not isinstance(item, BetaMessage | Exception):
            raise TypeError(f"script items are BetaMessage or Exception, got {type(item).__name__}")
        if isinstance(item, Exception):
            continue
        if item.id in message_ids:
            raise ValueError(f"two scripted responses share id {item.id!r}: pass msg_id= to one")
        message_ids.add(item.id)
        for block in item.content:
            if block.type == "tool_use":
                if block.id in call_ids:
                    raise ValueError(f"tool_use id {block.id!r} appears in two scripted responses")
                call_ids.add(block.id)


# ── builders: content blocks as the API sends them ──────────────────────────────────────────


def text(t: str) -> Block:
    return {"type": "text", "text": t}


def tool_use(name: str, args: Mapping[str, object], *, tool_use_id: str) -> Block:
    return {"type": "tool_use", "id": tool_use_id, "name": name, "input": copy.deepcopy(dict(args))}


def thinking(thinking: str = "", *, signature: str = "sig-fake") -> Block:
    """Sonnet 5.5's default `display: "omitted"` sends the block with empty text + a signature."""
    return {"type": "thinking", "thinking": thinking, "signature": signature}


def redacted_thinking(data: str = "redacted-fake") -> Block:
    return {"type": "redacted_thinking", "data": data}


def message(
    *blocks: Block,
    stop_reason: BetaStopReason = "end_turn",
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_read: int = 0,
    cache_write: int = 0,
    model: str = "claude-sonnet-5-5",
    msg_id: str | None = None,
    refusal_category: RefusalCategory | None = None,
) -> BetaMessage:
    """A whole response, validated by the SDK model (an unknown block shape raises).

    `msg_id` defaults to a hash of the response, so it's deterministic and differs between
    different responses. `refusal` and `max_tokens` may carry partial output: A6 must discard it.
    """
    _check_stop_reason(blocks, stop_reason, refusal_category)
    stop_details = (
        {"type": "refusal", "category": refusal_category, "explanation": None}
        if stop_reason == "refusal"
        else None
    )
    payload: dict[str, Any] = copy.deepcopy(  # the message owns its data (blocks can be reused)
        {
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": list(blocks),
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "stop_details": stop_details,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_creation_input_tokens": cache_write,
                "cache_read_input_tokens": cache_read,
            },
        }
    )
    if msg_id is None:
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode())
        msg_id = f"msg_fake_{digest.hexdigest()[:16]}"
    return BetaMessage.model_validate({"id": msg_id, **payload})


def _check_stop_reason(
    blocks: Sequence[Block], stop_reason: BetaStopReason, refusal_category: RefusalCategory | None
) -> None:
    calls = [block.get("id") for block in blocks if block.get("type") == "tool_use"]
    if stop_reason == "tool_use" and not calls:
        raise ValueError("stop_reason 'tool_use' needs at least one tool_use block")
    if stop_reason in ("end_turn", "stop_sequence") and calls:
        raise ValueError(f"stop_reason {stop_reason!r} never comes with tool_use blocks")
    repeated = sorted({str(call) for call in calls if calls.count(call) > 1})
    if repeated:
        raise ValueError(f"duplicate tool_use id {repeated[0]!r} in one response")
    if refusal_category is not None and stop_reason != "refusal":
        raise ValueError("refusal_category only goes with stop_reason 'refusal'")


def end_turn(reply: str, *, msg_id: str | None = None) -> BetaMessage:
    return message(text(reply), msg_id=msg_id)


def tool_round(*blocks: Block, msg_id: str | None = None) -> BetaMessage:
    """A `tool_use` stop. Pass `thinking()` / `text()` blocks too, in the order the API would."""
    return message(*blocks, stop_reason="tool_use", msg_id=msg_id)


def refusal(category: RefusalCategory | None = None) -> BetaMessage:
    """A safety decline before any output: empty content. The API may send no category."""
    return message(stop_reason="refusal", output_tokens=0, refusal_category=category)


def cut_off(partial: str) -> BetaMessage:
    return message(text(partial), stop_reason="max_tokens")
