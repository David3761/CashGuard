"""Security review P1-6 / P1-11: security headers, the body size limit, the docs switch, CORS,
and the bounded soft-note value."""

from collections.abc import AsyncIterator

import pytest
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.main import create_app
from app.security.http_hardening import API_CSP, DOCS_CSP, HSTS, MAX_BODY_BYTES
from app.services import users
from tests import factories as f


def settings(**kw) -> Settings:
    return Settings(_env_file=None, SIM_CLOCK_FROM_DB=False, **kw)


async def test_every_api_response_carries_the_security_headers(make_client):
    async with make_client(create_app(settings(SIM_MODE=False))) as c:
        r = await c.get("/api/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert r.headers["content-security-policy"] == API_CSP
    assert r.headers["cache-control"] == "no-store"
    assert r.headers["strict-transport-security"] == HSTS


async def test_errors_carry_the_headers_too(make_client):
    async with make_client(create_app(settings(SIM_MODE=False))) as c:
        r = await c.get("/api/me")  # 401: no token
    assert r.status_code == 401
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["content-security-policy"] == API_CSP


async def test_no_hsts_over_plain_http_in_sim_mode_but_over_https_yes(make_client):
    app = create_app(settings(SIM_MODE=True))
    async with make_client(app) as c:
        r = await c.get("/api/health")
    assert "strict-transport-security" not in r.headers
    async with make_client(app) as c:
        r = await c.get("https://test/api/health")
    assert r.headers["strict-transport-security"] == HSTS


async def test_a_streamed_response_passes_through_with_the_headers(make_client):
    app = create_app(settings(SIM_MODE=False))

    async def events() -> AsyncIterator[bytes]:
        for n in range(3):
            yield f"data: {n}\n\n".encode()

    @app.get("/api/_test/stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(events(), media_type="text/event-stream")

    async with make_client(app) as c:
        r = await c.get("/api/_test/stream")
    assert r.text == "data: 0\n\ndata: 1\n\ndata: 2\n\n"
    assert r.headers["content-type"].startswith("text/event-stream")
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_a_body_over_64_kib_is_413_before_anything_runs(make_client):
    async with make_client(create_app(settings())) as c:
        r = await c.post("/api/chat", content=b"x" * (MAX_BODY_BYTES + 1))
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_a_chunked_body_over_the_limit_is_413_too(make_client):
    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(5):
            yield b"x" * (MAX_BODY_BYTES // 4)

    async with make_client(create_app(settings())) as c:
        r = await c.post("/api/chat", content=chunks())
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


async def test_a_body_under_the_limit_is_read_normally(make_client):
    async with make_client(create_app(settings())) as c:
        r = await c.post("/api/chat", json={"text": "salut"})
    assert r.status_code == 401  # it got as far as the auth check


@pytest.mark.parametrize("enabled", [True, False])
async def test_docs_follow_api_docs_enabled(make_client, enabled):
    async with make_client(create_app(settings(API_DOCS_ENABLED=enabled))) as c:
        docs = await c.get("/api/docs")
        schema = await c.get("/api/openapi.json")
    assert docs.status_code == schema.status_code == (200 if enabled else 404)
    if enabled:
        assert docs.headers["content-security-policy"] == DOCS_CSP


def test_docs_are_off_by_default():
    assert Settings(_env_file=None).API_DOCS_ENABLED is False


async def test_no_cors_headers_for_a_browser_origin(make_client):
    async with make_client(create_app(settings())) as c:
        r = await c.get("/api/health", headers={"Origin": "https://evil.example"})
        pre = await c.options(
            "/api/chat",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
    assert "access-control-allow-origin" not in r.headers
    assert "access-control-allow-origin" not in pre.headers


async def test_a_soft_note_is_bounded(as_user, db):
    u = await f.user(db)
    await users.set_onboarded(db, u.id)
    ok = await as_user(u).patch("/life-profile/what_works", json={"value": ["gătit acasă"]})
    assert ok.status_code == 200
    big = await as_user(u).patch("/life-profile/what_works", json={"value": "x" * 2001})
    assert big.status_code == 422
    assert big.json()["error"]["code"] == "validation_error"
