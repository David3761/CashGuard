"""WebSocket: one socket set per user, push only after the DB commit (arch 5.2, B7).

In-memory, so uvicorn runs with 1 worker. The DB is the truth; the socket only notifies.

Abuse limits (security review P1-7): at most `MAX_SOCKETS_PER_USER` sockets per user, the
`ws_connect` rate limit per principal, inbound frames of at most `MAX_INBOUND_BYTES` (the
client never sends commands; uvicorn's `--ws-max-size` caps frames at the server too), and the
token's `exp` re-checked on every inbound message and every ping: an expired token closes the
socket with 4401 (the app refreshes its token and reconnects). Close codes: 1008 bad token,
1009 frame too big, 4401 token expired, 4409 too many sockets, 4429 rate limited.
"""

import asyncio
import contextlib
import logging
from collections.abc import Mapping
from typing import Any, Final, Protocol

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.auth import ws_auth
from app.db.session import session_factory
from app.errors import DomainError
from app.events import Event
from app.security import ratelimit

log = logging.getLogger(__name__)
PING_SECONDS = 30.0
MAX_SOCKETS_PER_USER: Final = 3
MAX_INBOUND_BYTES: Final = 4096
CLOSE_BAD_TOKEN: Final = 1008
CLOSE_TOO_BIG: Final = 1009
CLOSE_TOKEN_EXPIRED: Final = 4401
CLOSE_TOO_MANY_SOCKETS: Final = 4409
CLOSE_RATE_LIMITED: Final = 4429
# Token times are Keycloak's real time, never the simulator's (tests swap this clock).
TOKEN_CLOCK: clock.Clock = clock.RealClock()


class Socket(Protocol):
    async def send_json(self, data: Any) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._sockets: dict[int, set[Socket]] = {}

    def connect(self, user_id: int, socket: Socket) -> None:
        self._sockets.setdefault(user_id, set()).add(socket)

    def disconnect(self, user_id: int, socket: Socket) -> None:
        sockets = self._sockets.get(user_id, set())
        sockets.discard(socket)
        if not sockets:
            self._sockets.pop(user_id, None)

    def count(self, user_id: int) -> int:
        return len(self._sockets.get(user_id, ()))

    async def push(self, user_id: int, event: Event) -> None:
        """Send to every socket of the user; a dead socket is dropped, the others still get it."""
        for socket in list(self._sockets.get(user_id, ())):
            try:
                await socket.send_json(event)
            except Exception:
                self.disconnect(user_id, socket)


manager = ConnectionManager()

_QUEUE = "ws_after_commit"


def push_after_commit(session: AsyncSession, user_id: int, event: Event) -> None:
    """Queue `event`; it's sent (in order) only if the session commits. A rollback drops it."""
    queue: list[tuple[int, Event]] | None = session.info.get(_QUEUE)
    if queue is None:
        queue = session.info[_QUEUE] = []
        sync = session.sync_session

        def after_commit(_: Any) -> None:
            pending = list(session.info.pop(_QUEUE, []))
            sa_event.remove(sync, "after_rollback", after_rollback)
            if pending:
                asyncio.get_running_loop().create_task(_send(pending))

        def after_rollback(_: Any) -> None:
            session.info.pop(_QUEUE, None)
            if sa_event.contains(sync, "after_commit", after_commit):
                sa_event.remove(sync, "after_commit", after_commit)

        sa_event.listen(sync, "after_commit", after_commit, once=True)
        sa_event.listen(sync, "after_rollback", after_rollback, once=True)
    queue.append((user_id, event))


async def _send(pending: list[tuple[int, Event]]) -> None:
    for user_id, event in pending:
        await manager.push(user_id, event)


router = APIRouter()


def token_expired(exp: object) -> bool:
    """True once the token's `exp` (seconds since the epoch) has passed on the real clock."""
    if not isinstance(exp, int | float):
        return True
    return TOKEN_CLOCK.now().timestamp() >= exp


def _too_big(message: Mapping[str, Any]) -> bool:
    text, data = message.get("text"), message.get("bytes")
    size = len(text.encode()) if isinstance(text, str) else len(data or b"")
    return size > MAX_INBOUND_BYTES


async def _close(websocket: WebSocket, code: int, reason: str) -> None:
    # accept first: closing before the handshake is an HTTP 403 on a real server, and the
    # app reads the WebSocket close code (arch 5.1, 9.4)
    await websocket.accept()
    await websocket.close(code=code, reason=reason)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    client = websocket.client.host if websocket.client else "unknown"
    principal = await ratelimit.key_for_token(token, f"ip:{client}")
    if ratelimit.check("ws_connect", principal) is not None:
        await _close(websocket, CLOSE_RATE_LIMITED, "rate_limited")
        return
    try:
        async with session_factory()() as db:
            user, claims = await ws_auth(db, token)
    except DomainError:
        await _close(websocket, CLOSE_BAD_TOKEN, "invalid_token")
        return
    exp = claims.raw.get("exp")
    if manager.count(user.id) >= MAX_SOCKETS_PER_USER:
        await _close(websocket, CLOSE_TOO_MANY_SOCKETS, "too_many_sockets")
        return
    await websocket.accept()
    manager.connect(user.id, websocket)  # no await since the count: the cap can't be raced

    async def ping() -> None:
        while True:
            await asyncio.sleep(PING_SECONDS)
            if token_expired(exp):
                await websocket.close(code=CLOSE_TOKEN_EXPIRED, reason="token_expired")
                return
            await websocket.send_json({"type": "ping", "data": {}})

    pinger = asyncio.create_task(ping())
    try:
        while True:
            # the client never sends commands; reading keeps the socket open
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if _too_big(message):
                await websocket.close(code=CLOSE_TOO_BIG, reason="message_too_big")
                break
            if token_expired(exp):
                await websocket.close(code=CLOSE_TOKEN_EXPIRED, reason="token_expired")
                break
    except (WebSocketDisconnect, RuntimeError):
        pass  # RuntimeError: the ping task closed the socket while we were reading
    finally:
        pinger.cancel()
        # the ping task may also have ended on a socket the client already dropped
        with contextlib.suppress(asyncio.CancelledError, RuntimeError, WebSocketDisconnect):
            await pinger
        manager.disconnect(user.id, websocket)
