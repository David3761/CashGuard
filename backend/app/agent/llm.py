"""The Claude client (A1): the one place where the backend talks to Claude.

`LLM` builds the arch 6.8 request and calls `AsyncAnthropic`. The agent loop (A6), proactive runs
(A7) and the eval runner (A10) depend on the `LLMClient` protocol, which `LLM` and the tests'
`FakeLLM` (`tests/fakes/fake_llm.py`) both satisfy, and fall back on the error types (arch §11).
Responses are the SDK's `BetaMessage`: `LLM` always uses the beta endpoint, so there's one
response type whether the refusal fallback is on or off (plan A1, D1).

The call is streamed internally (`get_final_message()`), so the read timeout bounds the silence
between two chunks, not the whole generation, and a stream that breaks midway is not re-generated
by the SDK's retries. The caller (A6/A7/B9) owns the overall deadline (`asyncio.timeout`).

Every failure becomes `LLMUnavailable` (transient, or no usable configuration) or `LLMBadRequest`
(Claude rejected our request), logged without the key or anything the user or Claude said.

At most `LLM_MAX_CONCURRENCY` calls are in flight per client (an `asyncio.Semaphore`): a burst of
runs queues for a slot instead of fanning out unbounded Bedrock calls (LLM10). The wait counts
toward the caller's deadline.
"""

import asyncio
import json
import logging
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Final, Protocol, cast

import anthropic
import httpx2
from anthropic import AsyncAnthropic, AsyncAnthropicBedrock
from anthropic.types.beta import BetaMessage, BetaMessageParam, BetaToolParam
from anthropic.types.beta.message_create_params import MessageCreateParamsBase
from pydantic import BaseModel

from app.config import Effort, Settings, get_settings

log = logging.getLogger(__name__)

# Arch 6.8. Never sent: temperature/top_p/top_k (a 400 on API version 2026-10-21) and tool_choice
# (the default "auto" is what we want; a forced "any"/"tool" is a 400 on Sonnet 5.5).
API_BASE_URL: Final = "https://api.anthropic.com"  # never ANTHROPIC_BASE_URL (review R3)
TIMEOUT_S: Final = 30.0  # streamed: connect, and the longest silence between two chunks
MAX_RETRIES: Final = 2  # the SDK retries a request that fails before its stream opens
MAX_CONCURRENCY: Final = 4  # the LLM_MAX_CONCURRENCY default
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


@dataclass(frozen=True)
class BedrockAuth:
    """Amazon Bedrock credentials (the hackathon's temporary AWS session); not in repr."""

    region: str
    access_key: str = field(default="", repr=False)
    secret_key: str = field(default="", repr=False)
    session_token: str | None = field(default=None, repr=False)
    api_key: str | None = field(default=None, repr=False)  # a Bedrock API key: wins over SigV4


class LLMError(Exception):
    """A Claude call failed. The caller answers with a template instead (arch §11).

    It carries only safe metadata, never request or response content: no cause or context is
    attached (the SDK's exceptions hold the response body or the streamed tool JSON).
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


class LLMUnavailable(LLMError):
    """Transient or not configured: rate limit, overload, 5xx, timeout, no network, a broken or
    incomplete stream, no API key (or headers from the environment)."""


class LLMBadRequest(LLMError):
    """Claude rejected our request: a bug or a config error, not retried.

    A 4xx other than 408/409/429, or a request-error event inside the stream (`status_code` 200).
    The request id finds the details in the Anthropic Console. The API's own message can quote the
    request, so it's only on `_api_message`, for a debugger: never in `str()` or a log.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_type: str | None = None,
        request_id: str | None = None,
        api_message: str | None = None,
    ) -> None:
        super().__init__(
            message, status_code=status_code, error_type=error_type, request_id=request_id
        )
        self._api_message = api_message


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


_TRANSIENT_4XX: Final = frozenset({408, 409, 429})  # the SDK retries these, like every 5xx
_REQUEST_ERROR_TYPES: Final = frozenset(
    {
        "invalid_request_error",
        "authentication_error",
        "billing_error",
        "permission_error",
        "not_found_error",
        "request_too_large",
    }
)


def classify(status: int, error_type: str | None) -> type[LLMUnavailable] | type[LLMBadRequest]:
    """Which error an API failure becomes. Pure.

    An HTTP error maps by its status: 408/409/429 and every 5xx are transient (and were already
    retried by the SDK); any other 4xx means our request was wrong. An `error` event inside a
    stream that opened with HTTP 200 maps by its type: only a request-error type is our fault.
    """
    if status >= 400:
        return LLMUnavailable if status in _TRANSIENT_4XX or status >= 500 else LLMBadRequest
    return LLMBadRequest if error_type in _REQUEST_ERROR_TYPES else LLMUnavailable


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
        bedrock: BedrockAuth | None = None,
        max_concurrency: int = MAX_CONCURRENCY,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._slots = asyncio.Semaphore(max_concurrency)  # bound to a loop on first use
        self._model = model
        self._effort = effort
        self._refusal_fallback = refusal_fallback
        self._http_client = http_client
        self._client: AsyncAnthropic | AsyncAnthropicBedrock | None = None
        if bedrock is not None:
            # On-demand Bedrock calls need the cross-region inference profile id
            # (`us.anthropic.claude-sonnet-5-5`); the server-side refusal fallback doesn't exist
            # there (Claude API only), so it is always off.
            self._model = bedrock_model_id(model, bedrock.region)
            if refusal_fallback:
                log.warning("ANTHROPIC_REFUSAL_FALLBACK is ignored on Bedrock (Claude API only)")
            self._refusal_fallback = False
            self._unavailable = _bedrock_unavailable_reason(bedrock)
        else:
            self._unavailable = _unavailable_reason(api_key)
        if self._unavailable is None:
            _neutralise_sdk_environment()
            if bedrock is not None:
                # Explicit credentials, region and endpoint: nothing comes from the environment.
                # bedrock-runtime (InvokeModel): the hackathon account has no Mantle endpoint.
                # The SDK refuses an API key together with AWS credentials: pass one or the other.
                sigv4 = not bedrock.api_key
                self._client = AsyncAnthropicBedrock(
                    api_key=bedrock.api_key or None,
                    aws_access_key=bedrock.access_key if sigv4 else None,
                    aws_secret_key=bedrock.secret_key if sigv4 else None,
                    aws_session_token=bedrock.session_token if sigv4 else None,
                    aws_region=bedrock.region,
                    base_url=f"https://bedrock-runtime.{bedrock.region}.amazonaws.com",
                    timeout=TIMEOUT_S,
                    max_retries=max_retries,
                    http_client=http_client,
                )
            else:
                # An explicit key and base URL: the SDK would otherwise read them from the
                # environment or an `ant auth login` profile.
                self._client = AsyncAnthropic(
                    api_key=api_key,
                    base_url=API_BASE_URL,
                    timeout=TIMEOUT_S,
                    max_retries=max_retries,
                    http_client=http_client,
                )

    @classmethod
    def from_settings(
        cls, settings: Settings, *, http_client: httpx2.AsyncClient | None = None
    ) -> "LLM":
        """The client the settings describe (arch §3). Secrets are unwrapped only here."""
        secret = settings.ANTHROPIC_API_KEY
        bedrock = None
        if settings.LLM_PROVIDER == "bedrock":
            access, key = settings.AWS_ACCESS_KEY_ID, settings.AWS_SECRET_ACCESS_KEY
            token, bearer = settings.AWS_SESSION_TOKEN, settings.AWS_BEARER_TOKEN_BEDROCK
            bedrock = BedrockAuth(
                region=settings.AWS_DEFAULT_REGION or "",
                access_key=access.get_secret_value() if access is not None else "",
                secret_key=key.get_secret_value() if key is not None else "",
                session_token=token.get_secret_value() if token is not None else None,
                api_key=bearer.get_secret_value() if bearer is not None else None,
            )
        return cls(
            api_key=secret.get_secret_value() if secret is not None else None,
            model=settings.ANTHROPIC_MODEL,
            effort=settings.ANTHROPIC_EFFORT,
            refusal_fallback=settings.ANTHROPIC_REFUSAL_FALLBACK,
            http_client=http_client,
            bedrock=bedrock,
            max_concurrency=settings.LLM_MAX_CONCURRENCY,
        )

    async def create(
        self,
        system: Sequence[str],
        messages: Sequence[BetaMessageParam],
        tools: Sequence[BetaToolParam] = (),
    ) -> BetaMessage:
        """One Messages API call, streamed internally; returns the whole `BetaMessage`.

        Raises `LLMUnavailable` (rate limit, overload, 5xx, timeout, no network, a broken or
        incomplete stream, or no usable configuration, in which case nothing is sent) or
        `LLMBadRequest` (Claude rejected the request). Cancellation reaches the caller unchanged.
        """
        params = build_params(
            system,
            messages,
            tools,
            model=self._model,
            effort=self._effort,
            refusal_fallback=self._refusal_fallback,
        )  # an invalid prompt is reported even without a key
        _check_json(params, "request")  # our bugs stay loud: nothing is sent (review A1.3 R3)
        if self._client is None:
            raise LLMUnavailable(self._unavailable or "the Claude client is not configured")
        failure: LLMError
        try:
            async with self._slots:  # LLM_MAX_CONCURRENCY calls in flight at most
                reply = await _read_stream(self._client, params)
        except anthropic.APIStatusError as err:  # before the stream, or an `error` event in it
            failure = _status_error(err)
        except (anthropic.APIConnectionError, httpx2.HTTPError) as err:  # incl. timeouts
            log.warning("Claude unreachable: %s", type(err).__name__)
            failure = LLMUnavailable("Claude API unreachable (connection error or timeout)")
        except _BrokenStream as err:
            failure = _unusable_stream(err.reason)
        except Exception as err:  # anything else the SDK raises while reading a malformed stream
            failure = _unusable_stream(f"the SDK couldn't read it ({type(err).__name__})")
        else:
            self._log_reply(reply)
            return reply
        # Raised outside the except blocks, so neither __cause__ nor __context__ holds the SDK's
        # exception (review A1.3 R1).
        raise failure

    def _log_reply(self, reply: BetaMessage) -> None:
        """Usage for every call (arch 6.8: check the cache hits); a warning for a refusal (R5)."""
        usage = reply.usage
        log.info(
            "Claude call: model=%s stop_reason=%s input_tokens=%s output_tokens=%s "
            "cache_read=%s cache_write=%s",
            reply.model,
            reply.stop_reason,
            usage.input_tokens,
            usage.output_tokens,
            usage.cache_read_input_tokens,
            usage.cache_creation_input_tokens,
        )
        if reply.stop_reason == "refusal":
            category = reply.stop_details.category if reply.stop_details else None
            log.warning(
                "Claude declined: category=%s model=%s refusal_fallback=%s",
                category,
                reply.model,
                "on" if self._refusal_fallback else "off",
            )

    async def aclose(self) -> None:
        """Close the HTTP connections (on app shutdown)."""
        if self._client is not None:
            await self._client.close()  # closes the injected http_client too
        elif self._http_client is not None:
            await self._http_client.aclose()


_llm: LLMClient | None = None  # the process's client, like app.clock's clock (Q4)


def get_llm() -> LLMClient:
    """The process's Claude client: built from the settings on first use, unless one was set."""
    global _llm
    if _llm is None:
        _llm = LLM.from_settings(get_settings())
    return _llm


def set_llm(llm: LLMClient | None) -> None:
    """Use this client (tests: a FakeLLM). None: build a fresh one from the settings next time."""
    global _llm
    _llm = llm


def _unavailable_reason(api_key: str | None) -> str | None:
    if not api_key:
        reason = "ANTHROPIC_API_KEY is not set"
        log.warning("Claude client disabled: %s; every agent reply will be a template", reason)
        return reason
    if os.environ.get("ANTHROPIC_CUSTOM_HEADERS") is not None:
        # The SDK merges these into every request (an auth header, a beta, even
        # anthropic-version) and they can't be stripped safely, so the client fails closed.
        reason = "ANTHROPIC_CUSTOM_HEADERS is set: unset it (Claude gets no headers from the env)"
        log.warning("Claude client disabled: %s", reason)
        return reason
    return None


def bedrock_model_id(model: str, region: str) -> str:
    """`claude-sonnet-5-5` -> `us.anthropic.claude-sonnet-5-5` (a full Bedrock id is kept)."""
    if "anthropic." in model:
        return model
    geo = {"us": "us", "eu": "eu", "ap": "apac"}.get(region.split("-", 1)[0], "us")
    return f"{geo}.anthropic.{model}"


def _bedrock_unavailable_reason(auth: BedrockAuth) -> str | None:
    needed = [("AWS_DEFAULT_REGION", auth.region)]
    if not auth.api_key:  # without a Bedrock API key, SigV4 needs the access key pair
        needed += [
            ("AWS_ACCESS_KEY_ID", auth.access_key),
            ("AWS_SECRET_ACCESS_KEY", auth.secret_key),
        ]
    missing = [name for name, value in needed if not value]
    if missing:
        reason = f"{', '.join(missing)} not set (LLM_PROVIDER=bedrock)"
        log.warning("Claude client disabled: %s; every agent reply will be a template", reason)
        return reason
    return _unavailable_reason("bedrock")  # the same ANTHROPIC_CUSTOM_HEADERS guard


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


def _status_error(err: anthropic.APIStatusError) -> LLMError:
    """The `LLMError` for an API error response (or an `error` event inside the stream)."""
    status, error_type, request_id = err.status_code, err.type, err.request_id
    where = f"HTTP {status}" if status >= 400 else "inside the stream"
    kind = error_type or "no error type"
    if classify(status, error_type) is LLMBadRequest:
        log.error("Claude rejected the request: %s, %s, request_id=%s", where, kind, request_id)
        return LLMBadRequest(
            f"Claude rejected the request ({where}, {kind}, request_id={request_id})",
            status_code=status,
            error_type=error_type,
            request_id=request_id,
            api_message=_api_message(err.body),
        )
    log.warning("Claude unavailable: %s, %s, request_id=%s", where, kind, request_id)
    return LLMUnavailable(
        f"Claude is unavailable ({where}, {kind})",
        status_code=status,
        error_type=error_type,
        request_id=request_id,
    )


def _api_message(body: object) -> str | None:
    """The API's own error message (it can quote the request: never log it), or None."""
    error = body.get("error") if isinstance(body, Mapping) else None
    message = error.get("message") if isinstance(error, Mapping) else None
    return message if isinstance(message, str) else None


class _BrokenStream(Exception):  # internal: always becomes LLMUnavailable
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _unusable_stream(reason: str) -> LLMUnavailable:
    log.warning("Claude's stream couldn't be used: %s", reason)
    return LLMUnavailable(f"Claude's stream couldn't be used: {reason}")


async def _read_stream(
    client: AsyncAnthropic | AsyncAnthropicBedrock, params: MessageCreateParamsBase
) -> BetaMessage:
    """Stream one response and return it whole, or raise `_BrokenStream`.

    Only a stream that started, reached `message_stop` and carries strict tool inputs is a message.
    """
    tool_json: dict[int, list[str]] = {}
    started = stopped = False
    # The Bedrock client exposes the same beta Messages surface under its own class, which mypy
    # can't unify with AsyncAnthropic's; the call and the stream events are the same.
    messages_api = cast("AsyncAnthropic", client).beta.messages
    async with messages_api.stream(**params) as stream:
        async for event in stream:
            if event.type == "message_start":
                started = True
            elif event.type == "message_stop":
                stopped = True
            elif event.type == "content_block_delta" and event.delta.type == "input_json_delta":
                tool_json.setdefault(event.index, []).append(event.delta.partial_json)
        if not started:
            raise _BrokenStream("no message in it")
        if not stopped:
            raise _BrokenStream("it ended before message_stop")
        final: BetaMessage | None = await stream.get_final_message()
    if final is None or final.stop_reason is None:  # `python -O` strips the SDK's own assert
        raise _BrokenStream("it ended before the message was complete")
    _check_tool_inputs(final, tool_json)
    # The stream helper builds Parsed* subclasses; hand out the plain types, exactly what a
    # non-streamed response (and FakeLLM) gives, built just as leniently.
    return BetaMessage.construct(None, **final.to_dict())  # None: fields set from the dict


def _check_tool_inputs(message: BetaMessage, tool_json: Mapping[int, list[str]]) -> None:
    """Refuse a tool call whose streamed input isn't complete, strict JSON (review A1.3 R8).

    The SDK parses streamed tool input leniently: a cut-off `{"amount": 50` (from 500) comes back
    as `{"amount": 50}`. Each input is re-parsed strictly from the raw chunks and must be exactly
    the object the SDK built; anything else would run a money tool on a guess.
    """
    calls = {index for index, block in enumerate(message.content) if block.type == "tool_use"}
    if not set(tool_json) <= calls:
        raise _BrokenStream("tool input JSON for a block that isn't a tool call")
    for index, block in enumerate(message.content):
        if block.type != "tool_use" or index not in tool_json:
            continue  # no deltas: the input came whole with the block's start
        text = "".join(tool_json[index])
        # A tool without arguments streams only empty chunks (Bedrock does): that input is {}.
        if (_strict_object(text) if text else {}) != block.input:
            raise _BrokenStream(f"the input of tool call {index} isn't complete, strict JSON")


def _strict_object(text: str) -> dict[str, object] | None:
    """A JSON object, parsed strictly (no NaN or Infinity, nothing after it), or None."""

    def no_constants(name: str) -> object:
        raise ValueError(f"{name} isn't JSON")

    try:
        value = json.loads(text, parse_constant=no_constants)
    except ValueError:  # incl. json.JSONDecodeError
        return None
    return value if isinstance(value, dict) else None


def _check_json(value: object, path: str) -> None:
    """Only strict JSON values may be sent: what's checked here is exactly what goes out.

    The SDK would quietly turn a `date` into a string and an int key into "7", and fail on NaN
    only once the stream is opening. `path` says where (never what) the bad value is.
    """
    if isinstance(value, BaseModel):  # a response block echoed back (A6)
        value = value.model_dump(mode="python", exclude_unset=True)
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} has a {type(key).__name__} key: JSON keys are strings")
            _check_json(item, f"{path}.{key}")
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            _check_json(item, f"{path}[{index}]")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"{path} is {value}: JSON has no NaN or Infinity")
    elif not (value is None or isinstance(value, str | int | float)):  # bool is an int
        raise TypeError(f"{path} is a {type(value).__name__}: not a JSON value")
