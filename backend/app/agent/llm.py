"""The Claude client (A1): the one place where the backend talks to Claude.

This module holds the error types the agent falls back on (arch §11) and the `LLMClient` protocol
that the agent loop (A6), proactive runs (A7) and the eval runner (A10) depend on. The tests'
`FakeLLM` (`tests/fakes/fake_llm.py`) satisfies it, and so will the real client (A1 step 2).
Responses are the SDK's `BetaMessage`: the client always uses the beta endpoint, so there's one
response type whether the refusal fallback is on or off (plan A1, D1).
"""

from collections.abc import Sequence
from typing import Final, Literal, Protocol

from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaToolParam

Effort = Literal["low", "medium", "high", "xhigh", "max"]

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
