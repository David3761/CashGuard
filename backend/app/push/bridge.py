"""Notifications → FCM pushes to the user's registered phones (the app API's devices).

Every user-visible nudge is a `notification.new` WebSocket event (B13 `notify`, and A7's
proactive question also creates a notification), pushed after its transaction commits through
`app.ws.manager.push`. The bridge sees each such event and sends one data message per device:
`{"message": body, "title", "type", "notification_id", "opens_chat"}` (all strings).

Hook: `install()` wraps `manager.push` once per process (ws.py is the integration's file and
isn't edited here). HANDOFF: when ws.py gets a listener API, register `PushBridge.on_event`
there instead. Without an FCM key the bridge only logs: it never touches the DB.
"""

import asyncio
import logging
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from app.db import models as m
from app.db.session import unit_of_work
from app.push.fcm import PushSender
from app.services import devices
from app.ws import manager

log = logging.getLogger(__name__)

EVENT = "notification.new"


def push_data(notification: Mapping[str, Any]) -> dict[str, str]:
    body = str(notification.get("body") or notification.get("title") or "")
    return {
        "message": body,
        "title": str(notification.get("title") or ""),
        "type": str(notification.get("type") or ""),
        "notification_id": str(notification.get("id") or ""),
        "opens_chat": "true" if notification.get("opens_chat") else "false",
    }


class PushBridge:
    def __init__(self, sender: PushSender | None) -> None:
        self.sender = sender
        self._tasks: set[asyncio.Task[int]] = set()

    def on_event(self, user_id: int, event: Mapping[str, Any]) -> None:
        """Called for every pushed event; schedules the delivery of notifications."""
        if event.get("type") != EVENT:
            return
        if self.sender is None:
            log.info("fcm disabled (no FCM_SERVICE_ACCOUNT_FILE): no push for user %s", user_id)
            return
        task = asyncio.get_running_loop().create_task(
            self.deliver(user_id, event.get("data") or {})
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def deliver(self, user_id: int, notification: Mapping[str, Any]) -> int:
        """Send to every device of the user's login; returns how many were sent."""
        if self.sender is None:
            return 0
        try:
            async with unit_of_work() as db:
                sub = await db.scalar(select(m.User.keycloak_sub).where(m.User.id == user_id))
                tokens = await devices.tokens_for(db, sub) if sub else []
            data = push_data(notification)
            results = [(token, await self.sender.send(token, data)) for token in tokens]
            dead = [token for token, result in results if result == "dead"]
            if dead:
                async with unit_of_work() as db:
                    await devices.remove_tokens(db, dead)
            return sum(result == "sent" for _, result in results)
        except Exception:
            log.exception("push for user %s failed", user_id)
            return 0


_bridge: PushBridge | None = None


def current() -> PushBridge | None:
    return _bridge


def install(bridge: PushBridge) -> None:
    """Make `bridge` see every `manager.push` (the wrapper is installed once per process)."""
    global _bridge
    _bridge = bridge
    if getattr(manager.push, "_push_bridge", False):
        return
    original = manager.push

    async def push(user_id: int, event: Any) -> None:
        await original(user_id, event)
        active = _bridge
        if active is not None:
            try:
                active.on_event(user_id, event)
            except Exception:
                log.exception("push bridge failed for user %s", user_id)

    push._push_bridge = True  # type: ignore[attr-defined]
    setattr(manager, "push", push)  # noqa: B010 - see the module docstring (no ws.py edit)
