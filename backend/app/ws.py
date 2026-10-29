"""WebSocket: one socket set per user, push only after the DB commit (arch 5.2, B7).

In-memory, so uvicorn runs with 1 worker. The DB is the truth; the socket only notifies.
"""

import asyncio
import contextlib
import logging
from typing import Any, Protocol

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import ws_user
from app.db.session import session_factory
from app.errors import DomainError
from app.events import Event

log = logging.getLogger(__name__)
PING_SECONDS = 30.0


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


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    try:
        async with session_factory()() as db:
            user = await ws_user(db, websocket.query_params.get("token"))
    except DomainError:
        # accept first: closing before the handshake is an HTTP 403 on a real server, and the
        # app expects the WebSocket close code 1008 (arch 5.1, 9.4) to refresh its token
        await websocket.accept()
        await websocket.close(code=1008)
        return
    await websocket.accept()
    manager.connect(user.id, websocket)

    async def ping() -> None:
        while True:
            await asyncio.sleep(PING_SECONDS)
            await websocket.send_json({"type": "ping", "data": {}})

    pinger = asyncio.create_task(ping())
    try:
        while True:
            await websocket.receive_text()  # the client never sends commands; keeps it open
    except WebSocketDisconnect:
        pass
    finally:
        pinger.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await pinger
        manager.disconnect(user.id, websocket)
