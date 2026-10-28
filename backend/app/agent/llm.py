"""The Claude client (A1): the one place where the backend talks to Claude.

`LLM` builds the arch 6.8 request and calls `AsyncAnthropic`. The agent loop (A6), proactive runs
(A7) and the eval runner (A10) depend on the `LLMClient` protocol, which `LLM` and the tests'
`FakeLLM` (`tests/fakes/fake_llm.py`) both satisfy, and fall back on the error types (arch §11).
Responses are the SDK's `BetaMessage`: `LLM` always uses the beta endpoint, so there's one
response type whether the refusal fallback is on or off (plan A1, D1).

The call is streamed internally (`get_final_message()`), so the read timeout bounds the silence
between two chunks, not the whole generation, and a stream that breaks midway is not re-generated
by the SDK's retries. The caller (A6/A7/B9) owns the overall deadline (`asyncio.timeout`).
"""

import logging
import os
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Final, Literal, Protocol

import httpx2
from anthropic import AsyncAnthropic
from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaToolParam
from anthropic.types.beta.message_create_params import MessageCreateParamsBase

log = logging.getLogger(__name__)

Effort = Literal["low", "medium", "high", "xhigh", "max"]

# Arch 6.8. Never sent: temperature/top_p/top_k (a 400 on API version 2026-10-21) and tool_choice
# (the default "auto" is what we want; a forced "any"/"tool" is a 400 on Sonnet 5.5).
API_BASE_URL: Final = "https://api.anthropic.com"  # never ANTHROPIC_BASE_URL (review R3)
TIMEOUT_S: Final = 30.0  # streamed: connect, and the longest silence between two chunks
MAX_RETRIES: Final = 2  # the SDK retries a request that fails before its stream opens
# Thinking counts toward max_tokens, and higher effort thinks more. `low` keeps the approved 8000;
# xhigh/max get the skill's streaming default (64 000, half of Sonnet 5.5's 128 000 limit). A cap
# costs nothing unless it's used.
MAX_TOKENS_BY_EFFORT: Final[Mapping[Effort, int]] = MappingProxyType(
    {"low": 8_000, "medium": 16_000, "high": 32_000, "xhigh": 64_000, "max": 64_000}
)
# With fallbacks="default" (D45: off by default). Claude API only. On Sonnet 5.5 it rescues only
# `cyber` and `frontier_llm` declines (served by Sonnet 5); other refusals stay refusals.
REFUSAL_FALLBACK_BETA: Final = "server-side-fallback-2026-07-01"

# One cache breakpoint per system part plus the automatic one on the conversation tail: the API
# allows at most 4 per request (arch 6.8 prompt caching).
MAX_SYSTEM_PARTS: Final = 3


class LLMError(Exception):
    """A Claude call failed. The caller answers with a template instead (arch §11)."""


class LLMUnavailable(LLMError):
    """Transient or not configured: rate limit, overload, 5xx, timeout, no network, no API key."""


class LLMBadRequest(LLMError):
    """Claude rejected our request (a 4xx other than 408/409/429): a bug or a config error.

    Not retried. The API's error details are kept so the log says what to fix.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_type: str | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_type = error_type
        self.request_id = request_id


class LLMClient(Protocol):
    """What the agent needs from Claude: one Messages API call."""

    async def create(
        self,
        system: Sequence[str],
        messages: Sequence[BetaMessageParam],
        tools: Sequence[BetaToolParam] = (),
    ) -> BetaMessage:
        """Send one request. `system` is the ordered parts (frozen rules, then the snapshot)."""
        ...


def check_system(system: Sequence[str]) -> tuple[str, ...]:
    """Validate the system prompt parts: 1 to 3, none blank.

    A bare `str` is rejected: it's a `Sequence[str]` too, and would become one part per character.
    """
    if isinstance(system, str):
        raise TypeError("system must be a sequence of parts, not a single str")
    parts = tuple(system)
    if not 1 <= len(parts) <= MAX_SYSTEM_PARTS:
        raise ValueError(f"system needs 1 to {MAX_SYSTEM_PARTS} parts, got {len(parts)}")
    for index, part in enumerate(parts):
        if not isinstance(part, str):
            raise TypeError(f"system part {index} must be a str, got {type(part).__name__}")
        if not part.strip():
            raise ValueError(f"system part {index} is empty (the API rejects blank text blocks)")
    return parts


def build_params(
    system: Sequence[str],
    messages: Sequence[BetaMessageParam],
    tools: Sequence[BetaToolParam],
    *,
    model: str,
    effort: Effort,
    refusal_fallback: bool,
) -> MessageCreateParamsBase:
    """The Messages API request for one call (arch 6.8). Pure: same inputs, same request.

    Every system part gets a cache breakpoint (frozen rules first, the snapshot last) and the
    top-level `cache_control` adds the automatic one on the growing conversation (D48). The LLM
    owns every breakpoint: a `cache_control` from the caller could exceed the API's 4, or clash
    with the tail's 5-minute TTL (both a 400), so it's rejected. Messages and tools go through
    unchanged, in order: a stable prefix is what the cache hits.
    """
    parts = check_system(system)
    if _caller_cache_markers(messages, tools):
        raise ValueError(
            "cache_control in messages or tools: the LLM places the cache breakpoints (arch 6.8)"
        )
    params: MessageCreateParamsBase = {
        "model": model,
        "max_tokens": MAX_TOKENS_BY_EFFORT[effort],
        "output_config": {"effort": effort},
        "system": [
            {"type": "text", "text": part, "cache_control": {"type": "ephemeral"}} for part in parts
        ],
        "messages": list(messages),
        "cache_control": {"type": "ephemeral"},
    }
    if tools:
        params["tools"] = list(tools)
    if refusal_fallback:
        params["betas"] = [REFUSAL_FALLBACK_BETA]
        params["fallbacks"] = "default"
    return params


def _caller_cache_markers(
    messages: Sequence[BetaMessageParam], tools: Sequence[BetaToolParam]
) -> bool:
    """Whether a tool, a message block or a tool_result's inner block sets `cache_control`.

    Only the places the API reads it: a tool's `input_schema` may well have a property of that name.
    """
    if any("cache_control" in tool for tool in tools):
        return True
    for each in messages:
        content: object = each["content"]
        for block in content if isinstance(content, list) else ():
            if isinstance(block, Mapping) and "cache_control" in block:
                return True
            inner = block.get("content") if isinstance(block, Mapping) else None
            if isinstance(inner, list) and any(
                isinstance(part, Mapping) and "cache_control" in part for part in inner
            ):
                return True
    return False


class LLM:
    """The Claude client: one `AsyncAnthropic`, shared by every run of the (single) worker.

    It owns the injected `http_client` and closes it in `aclose()`, key or no key.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        effort: Effort,
        refusal_fallback: bool,
        max_retries: int = MAX_RETRIES,
        http_client: httpx2.AsyncClient | None = None,
    ) -> None:
        self._model = model
        self._effort = effort
        self._refusal_fallback = refusal_fallback
        self._http_client = http_client
        self._unavailable = _unavailable_reason(api_key)
        self._client: AsyncAnthropic | None = None
        if self._unavailable is None:
            _neutralise_sdk_environment()
            # An explicit key and base URL: the SDK would otherwise read them from the
            # environment or an `ant auth login` profile.
            self._client = AsyncAnthropic(
                api_key=api_key,
                base_url=API_BASE_URL,
                timeout=TIMEOUT_S,
                max_retries=max_retries,
                http_client=http_client,
            )

    async def create(
        self,
        system: Sequence[str],
        messages: Sequence[BetaMessageParam],
        tools: Sequence[BetaToolParam] = (),
    ) -> BetaMessage:
        """One Messages API call, streamed internally; returns the whole `BetaMessage`.

        No usable configuration (no key, environment headers) → `LLMUnavailable`, nothing sent.
        Other failures still surface as the SDK's own exceptions (mapped in A1 step 3).
        """
        params = build_params(
            system,
            messages,
            tools,
            model=self._model,
            effort=self._effort,
            refusal_fallback=self._refusal_fallback,
        )  # an invalid prompt is reported even without a key
        if self._client is None:
            raise LLMUnavailable(self._unavailable or "the Claude client is not configured")
        async with self._client.beta.messages.stream(**params) as stream:
            final = await stream.get_final_message()
        # The stream helper builds Parsed* subclasses; hand out the plain types, exactly what a
        # non-streamed response (and FakeLLM) gives, built just as leniently.
        return BetaMessage.construct(None, **final.to_dict())  # None: fields set from the dict

    async def aclose(self) -> None:
        """Close the HTTP connections (on app shutdown)."""
        if self._client is not None:
            await self._client.close()  # closes the injected http_client too
        elif self._http_client is not None:
            await self._http_client.aclose()


def _unavailable_reason(api_key: str | None) -> str | None:
    if not api_key:
        return "ANTHROPIC_API_KEY is not set"
    if os.environ.get("ANTHROPIC_CUSTOM_HEADERS") is not None:
        # The SDK merges these into every request (an auth header, a beta, even
        # anthropic-version) and they can't be stripped safely, so the client fails closed.
        reason = "ANTHROPIC_CUSTOM_HEADERS is set: unset it (Claude gets no headers from the env)"
        log.warning("Claude client disabled: %s", reason)
        return reason
    return None


def _neutralise_sdk_environment() -> None:
    """Undo what the SDK takes from the environment that would leak the key or user data."""
    if os.environ.get("ANTHROPIC_BASE_URL"):
        log.warning("ANTHROPIC_BASE_URL is ignored: Claude is always called at %s", API_BASE_URL)
    if os.environ.get("ANTHROPIC_LOG"):
        # Read when `anthropic` is imported: at debug the SDK logs whole request bodies.
        for name in ("anthropic", "httpx2"):
            sdk_logger = logging.getLogger(name)
            if sdk_logger.getEffectiveLevel() < logging.WARNING:
                sdk_logger.setLevel(logging.WARNING)
        log.warning("ANTHROPIC_LOG is ignored: the SDK's debug logs would contain user data")
