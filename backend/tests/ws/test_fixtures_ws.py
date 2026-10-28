"""F3 step 2: the WebSocket fixture (ws_connect) with the test key."""

import pytest
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from app.auth import verify_token
from app.errors import DomainError


@pytest.fixture
def echo_app(app):
    @app.websocket("/_test/ws")
    async def echo(websocket: WebSocket) -> None:
        try:
            claims = await verify_token(websocket.query_params.get("token", ""))
        except DomainError:
            await websocket.close(code=1008)
            return
        await websocket.accept()
        await websocket.send_json({"sub": claims.sub})
        await websocket.close()

    return app


def test_ws_connect_sends_the_users_token(echo_app, ws_connect):
    with ws_connect("a0000000-0000-4000-8000-000000000002", path="/_test/ws") as ws:
        assert ws.receive_json() == {"sub": "a0000000-0000-4000-8000-000000000002"}


def test_ws_connect_with_a_bad_token_is_closed_1008(echo_app, ws_connect):
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        ws_connect("x", path="/_test/ws", token="garbage") as ws,
    ):
        ws.receive_json()
    assert closed.value.code == 1008
