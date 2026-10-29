"""app.security.ratelimit: named token buckets per principal, the dependency, the guard.

Time is moved by installing later `FixedClock`s: no test sleeps.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI
from hypothesis import given
from hypothesis import strategies as st

from app.clock import FixedClock
from app.config import Settings
from app.errors import install_error_handlers
from app.security import ratelimit
from app.security.ratelimit import (
    Busy,
    ConcurrencyGuard,
    Decision,
    Limit,
    RateLimiter,
    RateLimits,
    bucket_limits,
    check,
    configure,
    key_for_token,
    one_at_a_time,
    principal_key,
    rate_limited,
)

T0 = datetime(2026, 10, 29, 4, 0, tzinfo=UTC)


class Time:
    """Moves a limiter's FixedClock forward."""

    def __init__(self, target: RateLimiter | RateLimits) -> None:
        self.target = target
        self.at = T0
        target.clock = FixedClock(T0)

    def advance(self, seconds: float) -> None:
        self.at += timedelta(seconds=seconds)
        self.target.clock = FixedClock(self.at)


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    ratelimit.reset()
    yield
    ratelimit.reset()


def limiter(*limits: Limit) -> tuple[RateLimiter, Time]:
    made = RateLimiter(*limits, clock=FixedClock(T0))
    return made, Time(made)


# ── token buckets ────────────────────────────────────────────────────────────────────────────


def test_a_burst_up_to_the_limit_then_refused_with_the_wait():
    lim, _ = limiter(Limit(3, 60))
    assert [lim.hit("k").allowed for _ in range(3)] == [True, True, True]
    refused = lim.hit("k")
    assert not refused.allowed
    assert refused.retry_after == pytest.approx(20.0)
    assert refused.retry_after_seconds == 20


def test_tokens_refill_over_time():
    lim, time = limiter(Limit(2, 60))
    lim.hit("k")
    lim.hit("k")
    time.advance(29.9)
    assert not lim.hit("k").allowed
    time.advance(0.2)
    assert lim.hit("k").allowed


def test_keys_are_independent():
    lim, _ = limiter(Limit(1, 60))
    assert lim.hit("user:a").allowed
    assert lim.hit("user:b").allowed
    assert not lim.hit("user:a").allowed


def test_every_limit_must_allow_and_the_longest_wait_wins():
    lim, time = limiter(Limit(10, 60), Limit(3, 86_400))
    assert all(lim.hit("k").allowed for _ in range(3))
    refused = lim.hit("k")
    assert not refused.allowed
    assert refused.retry_after == pytest.approx(86_400 / 3)
    time.advance(60)  # the minute bucket is full again, the day bucket isn't
    assert not lim.hit("k").allowed


def test_a_refused_attempt_takes_no_token():
    lim, time = limiter(Limit(1, 10), Limit(100, 1000))
    lim.hit("k")
    for _ in range(50):
        assert not lim.hit("k").allowed  # doesn't drain the day bucket
    time.advance(10)
    assert lim.hit("k").allowed


def test_a_clock_that_goes_back_refills_nothing():
    lim, time = limiter(Limit(1, 60))
    time.advance(100)
    lim.hit("k")
    time.advance(-50)
    assert not lim.hit("k").allowed


def test_memory_is_bounded(monkeypatch):
    monkeypatch.setattr(ratelimit, "MAX_KEYS", 5)
    lim, _ = limiter(Limit(1, 60))
    for i in range(50):
        lim.hit(f"k{i}")
    assert lim.keys() <= 5


@pytest.mark.parametrize(("count", "per"), [(0, 60), (1, 0), (-1, 1), (1, -5)])
def test_bad_limits_are_rejected(count, per):
    with pytest.raises(ValueError, match="count >= 1"):
        Limit(count, per)


def test_a_limiter_needs_a_limit():
    with pytest.raises(ValueError, match="at least one Limit"):
        RateLimiter()


def test_decision_retry_after_seconds():
    assert Decision(True).retry_after_seconds == 0
    assert Decision(False, 0.01).retry_after_seconds == 1
    assert Decision(False, 2.2).retry_after_seconds == 3


@given(st.integers(1, 20), st.lists(st.floats(0, 30), max_size=60))
def test_never_more_hits_than_the_budget(count, gaps):
    lim, time = limiter(Limit(count, 60))
    allowed = 0
    for gap in gaps:
        time.advance(gap)
        allowed += lim.hit("k").allowed
    assert allowed <= count + sum(gaps) * count / 60 + 1e-6


# ── named buckets from the settings ─────────────────────────────────────────────────────────


def test_default_buckets():
    assert bucket_limits(Settings(_env_file=None)) == {
        "chat": (Limit(10, 60), Limit(200, 86_400)),
        "sim": (Limit(30, 60),),
        "ws_connect": (Limit(10, 60),),
    }


def test_buckets_follow_the_settings(monkeypatch):
    for name, value in {
        "RATE_LIMIT_CHAT_PER_MINUTE": "3",
        "RATE_LIMIT_CHAT_PER_DAY": "30",
        "RATE_LIMIT_SIM_PER_MINUTE": "2",
        "RATE_LIMIT_WS_CONNECT_PER_MINUTE": "4",
    }.items():
        monkeypatch.setenv(name, value)
    assert bucket_limits(Settings(_env_file=None)) == {
        "chat": (Limit(3, 60), Limit(30, 86_400)),
        "sim": (Limit(2, 60),),
        "ws_connect": (Limit(4, 60),),
    }


@pytest.mark.parametrize(
    "name",
    [
        "RATE_LIMIT_CHAT_PER_MINUTE",
        "RATE_LIMIT_CHAT_PER_DAY",
        "RATE_LIMIT_SIM_PER_MINUTE",
        "RATE_LIMIT_WS_CONNECT_PER_MINUTE",
    ],
)
def test_limits_must_be_positive(monkeypatch, name):
    monkeypatch.setenv(name, "0")
    with pytest.raises(ValueError, match=name):
        Settings(_env_file=None)


def test_buckets_are_independent_and_unknown_ones_are_an_error():
    limits = RateLimits({"a": [Limit(1, 60)], "b": [Limit(1, 60)]}, clock=FixedClock(T0))
    assert limits.hit("a", "k").allowed
    assert limits.hit("b", "k").allowed
    assert not limits.hit("a", "k").allowed
    with pytest.raises(ValueError, match=r"unknown rate-limit bucket 'c' \(known: a, b\)"):
        limits.hit("c", "k")


def test_check_returns_none_or_the_seconds_to_wait():
    limits = configure(Settings(_env_file=None, RATE_LIMIT_WS_CONNECT_PER_MINUTE=2))
    time = Time(limits)
    assert check("ws_connect", "user:s") is None
    assert check("ws_connect", "user:s") is None
    assert check("ws_connect", "user:s") == 30
    time.advance(30)
    assert check("ws_connect", "user:s") is None


def test_configure_starts_clean():
    configure(Settings(_env_file=None, RATE_LIMIT_SIM_PER_MINUTE=1))
    assert check("sim", "k") is None
    assert check("sim", "k") is not None
    configure(Settings(_env_file=None, RATE_LIMIT_SIM_PER_MINUTE=1))
    assert check("sim", "k") is None


# ── the dependency: principal keys and both error shapes ──────────────────────────────────


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    api = APIRouter(prefix="/api")

    @api.post("/sim", dependencies=[Depends(rate_limited("sim"))])
    async def sim() -> dict[str, bool]:
        return {"ok": True}

    @api.get("/who")
    async def who(key: Annotated[str, Depends(principal_key)]) -> dict[str, str]:
        return {"key": key}

    app.include_router(api)
    configure(settings, clock=FixedClock(T0))
    return app


def _client(app: FastAPI, ip: str = "10.0.0.1") -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(ip, 1234))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_api_429_is_the_envelope_with_retry_after():
    app = _app(Settings(_env_file=None, RATE_LIMIT_SIM_PER_MINUTE=1))
    async with _client(app) as c:
        assert (await c.post("/api/sim")).status_code == 200
        r = await c.post("/api/sim")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"
    assert r.json() == {
        "error": {"code": "rate_limited", "message": "Too many requests. Try again in 60 seconds."}
    }


async def test_a_valid_token_keys_by_user_not_by_ip(test_jwks, make_token):
    app = _app(Settings(_env_file=None, RATE_LIMIT_SIM_PER_MINUTE=1))
    matei = {"Authorization": f"Bearer {make_token(sub='sub-matei')}"}
    ioana = {"Authorization": f"Bearer {make_token(sub='sub-ioana')}"}
    async with _client(app) as c:  # same proxy IP for everyone
        assert (await c.get("/api/who", headers=matei)).json() == {"key": "user:sub-matei"}
        assert (await c.post("/api/sim", headers=matei)).status_code == 200
        assert (await c.post("/api/sim", headers=ioana)).status_code == 200
        assert (await c.post("/api/sim", headers=matei)).status_code == 429


async def test_no_or_a_bad_token_falls_back_to_the_client_address(test_jwks):
    app = _app(Settings(_env_file=None))
    async with _client(app, "10.9.8.7") as c:
        assert (await c.get("/api/who")).json() == {"key": "ip:10.9.8.7"}
        bad = {"Authorization": "Bearer not-a-jwt"}
        assert (await c.get("/api/who", headers=bad)).json() == {"key": "ip:10.9.8.7"}
        basic = {"Authorization": "Basic abc"}
        assert (await c.get("/api/who", headers=basic)).json() == {"key": "ip:10.9.8.7"}


async def test_key_for_token_for_the_websocket_handshake(test_jwks, make_token):
    assert await key_for_token(make_token(sub="s1"), "ip:x") == "user:s1"
    assert await key_for_token(None, "ip:x") == "ip:x"
    assert await key_for_token("garbage", "ip:x") == "ip:x"


# ── one at a time ───────────────────────────────────────────────────────────────────────────


async def test_one_at_a_time_refuses_a_second_holder_and_frees_on_exit():
    async with one_at_a_time("user:1"):
        with pytest.raises(Busy) as busy:
            async with one_at_a_time("user:1", code="agent_busy", message="Still answering."):
                pass
        assert (busy.value.status, busy.value.code, busy.value.message) == (
            409,
            "agent_busy",
            "Still answering.",
        )
        async with one_at_a_time("user:2"):  # another key is free
            pass
    async with one_at_a_time("user:1"):  # released
        pass


async def test_one_at_a_time_releases_on_error():
    with pytest.raises(RuntimeError):
        async with one_at_a_time("k"):
            raise RuntimeError("boom")
    assert not ratelimit.guard().held("k")


async def test_concurrent_claims_have_exactly_one_winner():
    gate = asyncio.Event()

    async def worker() -> str:
        try:
            async with one_at_a_time("k"):
                await gate.wait()
                return "ran"
        except Busy:
            return "busy"

    tasks = [asyncio.create_task(worker()) for _ in range(20)]
    await asyncio.sleep(0)  # every task reaches its claim before anyone finishes
    gate.set()
    results = await asyncio.gather(*tasks)
    assert results.count("ran") == 1
    assert results.count("busy") == 19


def test_guard_claim_and_release():
    guard = ConcurrencyGuard()
    assert guard.claim("u1")
    assert not guard.claim("u1")
    assert guard.claim("u2")
    guard.release("u1")
    assert not guard.held("u1")
    assert guard.claim("u1")
    guard.release("never-held")  # no error
