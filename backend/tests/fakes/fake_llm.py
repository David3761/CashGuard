"""`FakeLLM`: the scripted stand-in for `app.agent.llm.LLM` in every non-live test (A1).

It returns the scripted responses in order, records a snapshot of every request, and fails
loudly when the script runs out. The builders return real, validated SDK objects
(`BetaMessage`) and reject shapes the API never sends (a `tool_use` stop without a call, repeated
ids…). In strict mode (the default) it also refuses every request the real API would answer with a
400 (tool_result pairing, prefill), a tool list or system prompt that changes within a run (D46),
and history edited before a replayed thinking block (preserved thinking). Not checked on purpose:
a scripted call to a tool the request didn't offer (A3/A7 test that defence).

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
from pydantic import BaseModel

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


class FakeLLMProtocolError(FakeLLMFailure):
    """A request the real API would reject (or that breaks D46). Nothing is served for it."""


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

    def __init__(self, script: Iterable[BetaMessage | Exception], *, strict: bool = True) -> None:
        self._script = list(script)
        _check_script(self._script)
        self._strict = strict
        self._next = 0
        self._overruns = 0
        self._served: list[tuple[RecordedRequest, BetaMessage]] = []  # (request, its response)
        self.requests: list[RecordedRequest] = []
        self.violations: list[str] = []

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
        request = RecordedRequest(parts, copy.deepcopy(list(messages)), copy.deepcopy(list(tools)))
        self.requests.append(request)
        number = len(self.requests)
        problems = self._problems(request) if self._strict else []
        if problems:
            self.violations.extend(problems)
            raise FakeLLMProtocolError(f"request {number} would be refused: " + "; ".join(problems))
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
        self._served.append((request, item))
        return item

    def _problems(self, request: RecordedRequest) -> list[str]:
        problems = _conversation_problems(request.messages)
        if self._served:  # D46: within a run, the tools and the system prompt stay as they were
            previous, response = self._served[-1]
            if _continues(request, previous, response):
                if request.tools != previous.tools:
                    problems.append(
                        "the tool list changed within a run (D46: tools_for runs once per run; "
                        "with thinking replayed, Sonnet 5.5 answers it with a 400)"
                    )
                if request.system != previous.system:
                    problems.append("the system prompt changed within a run (arch 6.3)")
        for producing, response in self._served:  # preserved thinking
            if _has_thinking(response) and not _replays_faithfully(request, producing, response):
                problems.append(
                    "a thinking block is replayed after its history, system prompt or tool set "
                    "changed (preserved thinking: a 400 for accounts created on or after "
                    "2026-08-31)"
                )
        return problems

    def assert_consumed(self) -> None:
        """Fail unless every response was used, no call overran, and no request was refused."""
        if self.violations:
            raise AssertionError(
                f"FakeLLM refused {len(self.violations)} violation(s): "
                + "; ".join(self.violations)
            )
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


# ── strict mode: the conversation rules of the real API ─────────────────────────────────────


def _get(block: object, name: str) -> object:
    """A field of a content block, whether it's a dict or an SDK model (an echoed response)."""
    return block.get(name) if isinstance(block, Mapping) else getattr(block, name, None)


def _blocks(message: BetaMessageParam) -> list[object]:
    content: object = message["content"]
    return list(content) if isinstance(content, list | tuple) else []


def _ids(message: BetaMessageParam, kind: str, field: str) -> list[str]:
    return [str(_get(block, field)) for block in _blocks(message) if _get(block, "type") == kind]


def _leading_results(message: BetaMessageParam | None) -> list[str]:
    """The ids of the tool_result blocks at the start of a user message."""
    if message is None or message["role"] != "user":
        return []
    leading = []
    for block in _blocks(message):
        if _get(block, "type") != "tool_result":
            break
        leading.append(str(_get(block, "tool_use_id")))
    return leading


def _conversation_problems(messages: Sequence[BetaMessageParam]) -> list[str]:
    """What the real API answers with a 400: the docs' tool-use rules, and prefill."""
    if not messages:
        return ["no messages"]
    problems = []
    if messages[0]["role"] != "user":
        problems.append("the first message must be the user's")
    if messages[-1]["role"] == "assistant":
        problems.append("the last message is the assistant's (prefill: a 400 on Sonnet 5.5)")
    for index, each in enumerate(messages):
        after = messages[index + 1] if index + 1 < len(messages) else None
        calls = _ids(each, "tool_use", "id") if each["role"] == "assistant" else []
        if calls and sorted(_leading_results(after)) != sorted(calls):
            problems.append(
                f"messages[{index + 1}] must start with exactly one tool_result for each tool call "
                f"of messages[{index}] {sorted(calls)}, got {_leading_results(after)}"
            )
        results = _ids(each, "tool_result", "tool_use_id") if each["role"] == "user" else []
        if len(results) > len(_leading_results(each)):
            problems.append(f"messages[{index}]: tool_result blocks must come first")
        before = messages[index - 1] if index > 0 else None
        if results and not (
            before and before["role"] == "assistant" and _ids(before, "tool_use", "id")
        ):
            problems.append(
                f"messages[{index}] has tool results, but messages[{index - 1}] called no tools"
            )
    return problems


def _canon(value: object) -> object:
    """A comparable form: SDK blocks as JSON, dicts and lists recursively, None-valued keys dropped
    (so a full `model_dump(mode="json")` echo equals the SDK blocks it came from)."""
    if isinstance(value, BaseModel):
        return _canon(value.model_dump(mode="json", exclude_unset=True))
    if isinstance(value, Mapping):
        return {key: _canon(item) for key, item in value.items() if item is not None}
    if isinstance(value, list | tuple):
        return [_canon(item) for item in value]
    return value


def _assistant(response: BetaMessage) -> object:
    return _canon({"role": "assistant", "content": response.content})


def _continues(request: RecordedRequest, previous: RecordedRequest, response: BetaMessage) -> bool:
    """Whether `request` is the next request of the same run: the previous response called tools,
    and the history was only appended to, with their results. After an `end_turn`, the next
    request (history + a new user message) starts a new run (arch 6.3)."""
    if response.stop_reason != "tool_use":
        return False
    expected = [_canon(each) for each in previous.messages] + [_assistant(response)]
    after = request.messages[len(expected)] if len(request.messages) > len(expected) else None
    return _canon(request.messages[: len(expected)]) == expected and bool(_leading_results(after))


def _has_thinking(response: BetaMessage) -> bool:
    return any(block.type in ("thinking", "redacted_thinking") for block in response.content)


def _replays_faithfully(
    request: RecordedRequest, producing: RecordedRequest, response: BetaMessage
) -> bool:
    """A replayed thinking block is valid only after the very same history, system and tool set."""
    turn = _assistant(response)
    for index, each in enumerate(request.messages):
        if _canon(each) == turn:
            return (
                _canon(request.messages[:index]) == _canon(producing.messages)
                and request.system == producing.system
                and _tool_set(request.tools) == _tool_set(producing.tools)
            )
    return True  # not replayed in this request


def _tool_set(tools: Sequence[BetaToolParam]) -> object:
    return _canon(sorted(tools, key=lambda tool: tool["name"]))  # the API binds it name-sorted


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
