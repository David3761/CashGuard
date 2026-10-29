"""The shared limiter on the app API: `{"message"}` + Retry-After, one principal ("app")."""

from collections.abc import Iterator
from datetime import UTC, datetime

import httpx
import pytest
from fastapi import APIRouter, Depends, FastAPI

from app.app_api.errors import MessageErrorRoute
from app.clock import FixedClock
from app.config import Settings
from app.errors import install_error_handlers
from app.security import ratelimit
from app.security.ratelimit import app_key, configure, rate_limited


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    ratelimit.reset()
    yield
    ratelimit.reset()


def _app(settings: Settings) -> FastAPI:
    app = FastAPI()
    install_error_handlers(app)
    anon = APIRouter(route_class=MessageErrorRoute)

    @anon.post("/assistant/messages", dependencies=[Depends(rate_limited("chat", key=app_key))])
    async def chat() -> dict[str, bool]:
        return {"ok": True}

    app.include_router(anon)
    configure(settings, clock=FixedClock(datetime(2026, 10, 29, 4, 0, tzinfo=UTC)))
    return app


def _client(app: FastAPI, ip: str) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, client=(ip, 1234))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_app_api_429_is_a_bare_message_with_retry_after():
    app = _app(Settings(_env_file=None, RATE_LIMIT_CHAT_PER_MINUTE=1))
    async with _client(app, "10.0.0.1") as c:
        assert (await c.post("/assistant/messages")).status_code == 200
        r = await c.post("/assistant/messages")
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"
    assert r.json() == {"message": "Too many requests. Try again in 60 seconds."}


async def test_the_app_api_is_one_principal_whatever_the_ip():
    app = _app(Settings(_env_file=None, RATE_LIMIT_CHAT_PER_MINUTE=1))
    async with _client(app, "10.0.0.1") as one, _client(app, "10.0.0.2") as two:
        assert (await one.post("/assistant/messages")).status_code == 200
        assert (await two.post("/assistant/messages")).status_code == 429
