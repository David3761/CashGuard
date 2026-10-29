"""app.push.bridge on committed data: notification.new → one data push per registered device."""

import asyncio
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select

from app import events
from app.db import models as m
from app.domain.models import NotificationView
from app.push import bridge
from app.push.fcm import PushResult
from app.services import devices
from app.ws import manager
from tests import factories as f


class FakeSender:
    def __init__(self, dead: set[str] | None = None) -> None:
        self.sent: list[tuple[str, dict[str, str]]] = []
        self.dead = dead or set()

    async def send(self, token: str, data: Mapping[str, str]) -> PushResult:
        self.sent.append((token, dict(data)))
        return "dead" if token in self.dead else "sent"


NOTE = {
    "id": 3,
    "type": "overspend",
    "title": "Buget",
    "body": "Ai depășit azi.",
    "opens_chat": True,
}


async def test_a_notification_reaches_every_device_and_dead_ones_are_dropped(db_committed):
    user = await f.user(db_committed)
    other = await f.user(db_committed)
    for token in ("t-1", "t-2"):
        await devices.upsert(
            db_committed, user.keycloak_sub, token, m.DevicePlatform.ANDROID, keep=5
        )
    await devices.upsert(db_committed, other.keycloak_sub, "t-other", m.DevicePlatform.IOS, keep=5)
    await db_committed.commit()
    sender = FakeSender(dead={"t-1"})

    sent = await bridge.PushBridge(sender).deliver(user.id, NOTE)

    assert sent == 1
    assert sorted(token for token, _ in sender.sent) == ["t-1", "t-2"]
    assert all(data["message"] == "Ai depășit azi." for _, data in sender.sent)
    left = await db_committed.scalars(
        select(m.Device.fcm_token).execution_options(populate_existing=True)
    )
    assert sorted(left) == ["t-2", "t-other"]


async def test_a_user_without_devices_gets_nothing(db_committed):
    user = await f.user(db_committed)
    await db_committed.commit()
    sender = FakeSender()
    assert await bridge.PushBridge(sender).deliver(user.id, NOTE) == 0
    assert sender.sent == []


class Sock:
    def __init__(self) -> None:
        self.got: list[str] = []

    async def send_json(self, data: Any) -> None:
        self.got.append(data["type"])


async def test_the_hook_sees_notifications_only_and_sockets_still_get_everything(db_committed):
    user = await f.user(db_committed)
    await devices.upsert(db_committed, user.keycloak_sub, "t-9", m.DevicePlatform.ANDROID, keep=5)
    await db_committed.commit()
    sender = FakeSender()
    previous = bridge.current()
    sock = Sock()
    manager.connect(user.id, sock)
    try:
        bridge.install(bridge.PushBridge(sender))
        bridge.install(bridge.PushBridge(sender))  # idempotent: one wrapper
        view = NotificationView.model_validate({**NOTE, "created_at": "2026-06-15T09:00:00Z"})
        await manager.push(user.id, events.notification_new(view))
        await manager.push(user.id, events.agent_typing())
        active = bridge.current()
        assert active is not None
        await asyncio.gather(*list(active._tasks))
    finally:
        manager.disconnect(user.id, sock)
        bridge.install(previous or bridge.PushBridge(None))
    assert sock.got == ["notification.new", "agent.typing"]
    assert [token for token, _ in sender.sent] == ["t-9"]


async def test_without_a_key_the_bridge_never_touches_the_db():
    quiet = bridge.PushBridge(None)
    quiet.on_event(1, {"type": "notification.new", "data": NOTE})
    assert quiet._tasks == set()
    assert await quiet.deliver(1, NOTE) == 0
