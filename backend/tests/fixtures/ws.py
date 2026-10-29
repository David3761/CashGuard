"""WebSocket fixtures (F3 step 2).

    def test_push(ws_connect, user):
        with ws_connect(user) as ws:          # opens /ws?token=<token for user>
            event = ws.receive_json()

Uses Starlette's TestClient, which runs the app in its own thread and event loop: WS tests use
`db_committed` data (committed rows), never the rolled-back `db` session.
"""

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager
from typing import Any

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient, WebSocketTestSession

from tests.fixtures.api import subject


@pytest.fixture
def ws_client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def ws_connect(
    ws_client: TestClient, make_token: Callable[..., str]
) -> Callable[..., AbstractContextManager[WebSocketTestSession]]:
    def _connect(
        user: Any, path: str = "/ws", token: str | None = None, **token_kw: Any
    ) -> AbstractContextManager[WebSocketTestSession]:
        token = token if token is not None else make_token(sub=subject(user), **token_kw)
        return ws_client.websocket_connect(f"{path}?token={token}")

    return _connect
