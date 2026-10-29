"""Security review P1-7: the /ws abuse limits (socket cap, frame size, token expiry, rate limit).

`ws_auth` is replaced by the real token check plus a fake user (no DB): Starlette's TestClient
runs the app in its own thread and event loop, and these tests are about the socket only.
"""

from contextlib import ExitStack
from datetime import date
from types import SimpleNamespace

import pytest
from starlette.websockets import WebSocketDisconnect

from app import clock
from app import ws as ws_module
from app.auth import verify_token
from app.config import Settings
from app.security import ratelimit

USER_IDS = {"sub-a": 9001, "sub-b": 9002}
FAR_FUTURE = clock.FixedClock.on(date(2100, 1, 1))


@pytest.fixture(autouse=True)
def fake_users(monkeypatch, test_jwks):
    async def ws_auth(db, token):
        claims = await verify_token(token or "")
        return SimpleNamespace(id=USER_IDS[claims.sub]), claims

    monkeypatch.setattr(ws_module, "ws_auth", ws_auth)


def closed_with(ws) -> int:
    with pytest.raises(WebSocketDisconnect) as closed:
        ws.receive_json()
    return closed.value.code


def test_three_sockets_per_user_are_fine_the_fourth_is_closed_4409(ws_connect):
    with ExitStack() as stack:
        for _ in range(ws_module.MAX_SOCKETS_PER_USER):
            stack.enter_context(ws_connect("sub-a"))
        assert ws_module.manager.count(USER_IDS["sub-a"]) == 3
        with ws_connect("sub-a") as fourth:
            assert closed_with(fourth) == ws_module.CLOSE_TOO_MANY_SOCKETS
        with ws_connect("sub-b"):  # another user is not affected
            assert ws_module.manager.count(USER_IDS["sub-b"]) == 1
    assert ws_module.manager.count(USER_IDS["sub-a"]) == 0


def test_an_inbound_frame_over_the_limit_is_closed_1009(ws_connect):
    with ws_connect("sub-a") as ws:
        ws.send_text("x" * (ws_module.MAX_INBOUND_BYTES + 1))
        assert closed_with(ws) == ws_module.CLOSE_TOO_BIG


def test_a_small_inbound_frame_keeps_the_socket_open(ws_connect, monkeypatch):
    monkeypatch.setattr(ws_module, "PING_SECONDS", 0.01)
    with ws_connect("sub-a") as ws:
        ws.send_text("hello")
        assert ws.receive_json()["type"] == "ping"


def test_a_message_after_the_token_expired_closes_4401(ws_connect, monkeypatch):
    with ws_connect("sub-a") as ws:
        monkeypatch.setattr(ws_module, "TOKEN_CLOCK", FAR_FUTURE)
        ws.send_text("still there?")
        assert closed_with(ws) == ws_module.CLOSE_TOKEN_EXPIRED


def test_an_idle_socket_is_closed_4401_at_the_ping_after_expiry(ws_connect, monkeypatch):
    monkeypatch.setattr(ws_module, "PING_SECONDS", 0.01)
    with ws_connect("sub-a") as ws:
        monkeypatch.setattr(ws_module, "TOKEN_CLOCK", FAR_FUTURE)
        assert closed_with(ws) == ws_module.CLOSE_TOKEN_EXPIRED


def test_token_expired_uses_the_real_clock_and_refuses_a_missing_exp():
    now = ws_module.TOKEN_CLOCK.now().timestamp()
    assert ws_module.token_expired(now - 1)
    assert not ws_module.token_expired(now + 60)
    assert ws_module.token_expired(None)


def test_connects_over_the_rate_limit_are_closed_4429(ws_connect):
    ratelimit.configure(Settings(_env_file=None, RATE_LIMIT_WS_CONNECT_PER_MINUTE=1))
    with ws_connect("sub-a"):
        pass
    with ws_connect("sub-a") as second:
        assert closed_with(second) == ws_module.CLOSE_RATE_LIMITED
    with ws_connect("sub-b") as other:  # keyed by user: another user still connects
        other.send_text("hi")
        assert ws_module.manager.count(USER_IDS["sub-b"]) == 1
