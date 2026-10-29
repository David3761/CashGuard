"""In-memory abuse protection: named token-bucket rate limits and a one-at-a-time guard.

Reusable by every route: the app API's chat today, `/api/chat`, `/api/sim` and the WebSocket
handshake next. The state lives in the process; that's fine because the app runs exactly one
uvicorn worker (arch 5.2).

**Buckets** are named, each with its own limits (`Settings`): `chat` 10/min + 200/day, `sim`
30/min, `ws_connect` 10/min. Every key gets one token bucket per limit; a hit passes only if every
bucket has a token, and only a hit that passes takes them (a refused attempt costs nothing).

**Keys are principals, not IPs:** behind Caddy every request comes from Caddy's address.
`principal_key` = `user:<sub>` from a valid Bearer token (bomboe's `verify_token`), else
`ip:<client>` as the last resort. The anonymous single-user app API uses `app_key` (`"app"`).

API:
- `rate_limited("chat")` → a FastAPI dependency; refused → 429 `rate_limited` + `Retry-After`
  (a `DomainError`, so `/api` answers with the arch 9.1 envelope and the app API with
  `{"message"}`).
- `check(bucket, key) -> retry_after_seconds | None`: for the WebSocket handshake.
- `one_at_a_time(key)`: an async context manager; a second holder → 409. The claim is atomic:
  the test-and-set has no `await` in between, and asyncio runs one coroutine at a time.

Time comes from an injectable `app.clock.Clock` (default: the **real** clock, not the
simulator's: abuse happens in real time). Tests pass `FixedClock`s and never sleep.
"""

import math
from collections.abc import AsyncIterator, Awaitable, Callable, Hashable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import Depends, Header, Request

from app import clock as app_clock
from app.config import Settings, get_settings
from app.errors import DomainError

MAX_KEYS: Final = 10_000  # per bucket; full buckets are forgotten first, so memory is bounded
BUSY_MESSAGE: Final = "Your previous request is still being handled. Try again in a moment."


@dataclass(frozen=True, slots=True)
class Limit:
    """`count` hits per `per_seconds`, refilled continuously (a burst of `count` is allowed)."""

    count: int
    per_seconds: float

    def __post_init__(self) -> None:
        if self.count < 1 or self.per_seconds <= 0:
            raise ValueError("a limit needs count >= 1 and per_seconds > 0")

    @property
    def rate(self) -> float:
        return self.count / self.per_seconds


@dataclass(frozen=True, slots=True)
class Decision:
    allowed: bool
    retry_after: float = 0.0  # seconds until the next hit would pass (0 when allowed)

    @property
    def retry_after_seconds(self) -> int:
        """For a `Retry-After` header: whole seconds, at least 1 when refused."""
        return 0 if self.allowed else max(1, math.ceil(self.retry_after))


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float


class RateLimiter:
    """One named bucket: token buckets per key, one per `Limit`."""

    def __init__(self, *limits: Limit, clock: app_clock.Clock | None = None) -> None:
        if not limits:
            raise ValueError("a RateLimiter needs at least one Limit")
        self.limits: tuple[Limit, ...] = limits
        self.clock: app_clock.Clock = clock or app_clock.RealClock()
        self._buckets: dict[Hashable, list[_Bucket]] = {}

    def _seconds(self) -> float:
        return self.clock.now().timestamp()

    def _refilled(self, key: Hashable, at: float) -> list[_Bucket]:
        buckets = self._buckets.get(key)
        if buckets is None:
            if len(self._buckets) >= MAX_KEYS:
                self._forget_full(at)
            buckets = [_Bucket(float(limit.count), at) for limit in self.limits]
            self._buckets[key] = buckets
        for bucket, limit in zip(buckets, self.limits, strict=True):
            elapsed = max(0.0, at - bucket.updated)  # a clock that goes back refills nothing
            bucket.tokens = min(float(limit.count), bucket.tokens + elapsed * limit.rate)
            bucket.updated = max(bucket.updated, at)
        return buckets

    def _forget_full(self, at: float) -> None:
        for key in list(self._buckets):
            buckets = self._refilled(key, at)
            if all(b.tokens >= lim.count for b, lim in zip(buckets, self.limits, strict=True)):
                del self._buckets[key]
        if len(self._buckets) >= MAX_KEYS:  # every key is busy: drop the oldest
            self._buckets.pop(next(iter(self._buckets)))

    def hit(self, key: Hashable) -> Decision:
        """Take one token from every bucket of `key`, or refuse without taking any."""
        at = self._seconds()
        buckets = self._refilled(key, at)
        waits = [
            (1.0 - bucket.tokens) / limit.rate
            for bucket, limit in zip(buckets, self.limits, strict=True)
            if bucket.tokens < 1.0
        ]
        if waits:
            return Decision(allowed=False, retry_after=max(waits))
        for bucket in buckets:
            bucket.tokens -= 1.0
        return Decision(allowed=True)

    def keys(self) -> int:
        return len(self._buckets)


def bucket_limits(settings: Settings) -> dict[str, tuple[Limit, ...]]:
    """The named buckets and their limits, from the settings."""
    return {
        "chat": (
            Limit(settings.RATE_LIMIT_CHAT_PER_MINUTE, 60.0),
            Limit(settings.RATE_LIMIT_CHAT_PER_DAY, 86_400.0),
        ),
        "sim": (Limit(settings.RATE_LIMIT_SIM_PER_MINUTE, 60.0),),
        "ws_connect": (Limit(settings.RATE_LIMIT_WS_CONNECT_PER_MINUTE, 60.0),),
    }


class RateLimits:
    """The registry of named buckets."""

    def __init__(
        self, buckets: Mapping[str, Sequence[Limit]], *, clock: app_clock.Clock | None = None
    ) -> None:
        self._clock: app_clock.Clock = clock or app_clock.RealClock()
        self._limiters = {
            name: RateLimiter(*limits, clock=self._clock) for name, limits in buckets.items()
        }

    @classmethod
    def from_settings(
        cls, settings: Settings, *, clock: app_clock.Clock | None = None
    ) -> "RateLimits":
        return cls(bucket_limits(settings), clock=clock)

    @property
    def clock(self) -> app_clock.Clock:
        return self._clock

    @clock.setter
    def clock(self, value: app_clock.Clock) -> None:
        """Tests move time by installing a later FixedClock."""
        self._clock = value
        for limiter in self._limiters.values():
            limiter.clock = value

    def names(self) -> frozenset[str]:
        return frozenset(self._limiters)

    def limiter(self, bucket: str) -> RateLimiter:
        try:
            return self._limiters[bucket]
        except KeyError:
            known = ", ".join(sorted(self._limiters))
            raise ValueError(f"unknown rate-limit bucket {bucket!r} (known: {known})") from None

    def hit(self, bucket: str, key: Hashable) -> Decision:
        return self.limiter(bucket).hit(key)


class ConcurrencyGuard:
    """At most one holder per key."""

    def __init__(self) -> None:
        self._held: set[Hashable] = set()

    def claim(self, key: Hashable) -> bool:
        """Atomic test-and-set (no await inside): False when `key` is already held."""
        if key in self._held:
            return False
        self._held.add(key)
        return True

    def release(self, key: Hashable) -> None:
        self._held.discard(key)

    def held(self, key: Hashable) -> bool:
        return key in self._held


# ── the process-wide registry and guard ──────────────────────────────────────────────────────

_limits: RateLimits | None = None
_guard = ConcurrencyGuard()


def configure(settings: Settings, *, clock: app_clock.Clock | None = None) -> RateLimits:
    """(Re)build the registry from `settings`, with empty buckets. Call it from the app factory;
    tests call it to start clean or to inject a clock."""
    global _limits
    _limits = RateLimits.from_settings(settings, clock=clock)
    return _limits


def limits() -> RateLimits:
    """The registry (built from `get_settings()` on first use if nobody configured it)."""
    return _limits if _limits is not None else configure(get_settings())


def guard() -> ConcurrencyGuard:
    return _guard


def reset() -> None:
    """Forget every bucket and every holder (tests)."""
    global _limits, _guard
    _limits = None
    _guard = ConcurrencyGuard()


def check(bucket: str, key: Hashable) -> int | None:
    """One hit on `bucket` for `key`: None if allowed, else the seconds to wait (≥ 1)."""
    decision = limits().hit(bucket, key)
    return None if decision.allowed else decision.retry_after_seconds


class RateLimited(DomainError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "rate_limited",
            f"Too many requests. Try again in {retry_after} seconds.",
            status=429,
            headers={"Retry-After": str(retry_after)},
        )
        self.retry_after = retry_after


class Busy(DomainError):
    def __init__(self, code: str = "busy", message: str = BUSY_MESSAGE) -> None:
        super().__init__(code, message, status=409)


@asynccontextmanager
async def one_at_a_time(
    key: Hashable, *, code: str = "busy", message: str = BUSY_MESSAGE
) -> AsyncIterator[None]:
    """Hold `key` for the block; a second concurrent holder gets `Busy` (409) at once."""
    held_by = _guard
    if not held_by.claim(key):
        raise Busy(code, message)
    try:
        yield
    finally:
        held_by.release(key)


# ── keys (principals) ─────────────────────────────────────────────────────────────────────────


def client_ip_key(request: Request) -> str:
    """The last resort: behind a proxy this is the proxy's address."""
    return f"ip:{request.client.host if request.client else 'unknown'}"


def app_key() -> str:
    """The app API: anonymous and single-user, so one principal."""
    return "app"


async def key_for_token(token: str | None, fallback: str) -> str:
    """`user:<sub>` for a valid token, else `fallback` (the WebSocket handshake's `?token=`)."""
    if token:
        from app.auth import verify_token

        try:
            return f"user:{(await verify_token(token)).sub}"
        except DomainError:
            pass
    return fallback


async def principal_key(
    request: Request, authorization: Annotated[str | None, Header()] = None
) -> str:
    """`user:<sub>` from a valid Bearer token (the JWT's user), else the client address. An
    invalid token isn't an error here: the route's own auth dependency answers 401."""
    scheme, _, token = (authorization or "").strip().partition(" ")
    bearer = token.strip() if scheme.lower() == "bearer" else None
    return await key_for_token(bearer, client_ip_key(request))


KeyDependency = Callable[..., Awaitable[str] | str]


def rate_limited(bucket: str, key: KeyDependency = principal_key) -> Callable[..., Awaitable[None]]:
    """A FastAPI dependency: one hit on `bucket` per request, keyed by `key` (a dependency
    returning the principal). Refused → `RateLimited` (429 + Retry-After)."""

    async def dependency(principal: Annotated[str, Depends(key)]) -> None:
        retry_after = check(bucket, principal)
        if retry_after is not None:
            raise RateLimited(retry_after)

    dependency.__name__ = f"rate_limited_{bucket}"
    return dependency
