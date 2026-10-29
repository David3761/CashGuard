"""Push devices (the app API, API_SPEC.md): one row per FCM token, owned by a login.

Rows are keyed by `user_sub` (users.keycloak_sub), not users.id, so a phone stays registered
across `/sim/reset` (which re-creates every user with a new id). Functions flush; the caller
commits (B3 rule).
"""

from collections.abc import Sequence

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m


async def upsert(
    db: AsyncSession, user_sub: str, fcm_token: str, platform: m.DevicePlatform, *, keep: int
) -> m.Device:
    """Register `fcm_token` (idempotent: a known token is updated, also moved to this login),
    then keep only the `keep` most recently updated devices of the login."""
    now = clock.now()
    stmt = (
        insert(m.Device)
        .values(
            fcm_token=fcm_token,
            platform=platform.value,
            user_sub=user_sub,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=[m.Device.fcm_token],
            set_={"platform": platform.value, "user_sub": user_sub, "updated_at": now},
        )
        .returning(m.Device.id)
    )
    device_id = (await db.execute(stmt)).scalar_one()
    stale = (
        select(m.Device.id)
        .where(m.Device.user_sub == user_sub)
        .order_by(m.Device.updated_at.desc(), m.Device.id.desc())
        .offset(keep)
    )
    await db.execute(delete(m.Device).where(m.Device.id.in_(stale.scalar_subquery())))
    await db.flush()
    row = await db.get(m.Device, device_id, populate_existing=True)
    if row is None:  # pragma: no cover - the row was just upserted in this transaction
        raise RuntimeError("the upserted device vanished")
    return row


async def remove(db: AsyncSession, user_sub: str, fcm_token: str) -> bool:
    """Unregister the login's token; True if a row was deleted (unknown tokens are fine)."""
    result = await db.execute(
        delete(m.Device).where(m.Device.user_sub == user_sub, m.Device.fcm_token == fcm_token)
    )
    await db.flush()
    return bool(getattr(result, "rowcount", 0))


async def tokens_for(db: AsyncSession, user_sub: str) -> list[str]:
    """The login's tokens, newest first."""
    rows = await db.scalars(
        select(m.Device.fcm_token)
        .where(m.Device.user_sub == user_sub)
        .order_by(m.Device.updated_at.desc(), m.Device.id.desc())
    )
    return list(rows)


async def remove_tokens(db: AsyncSession, tokens: Sequence[str]) -> None:
    """Drop tokens FCM reported as dead (any owner)."""
    if tokens:
        await db.execute(delete(m.Device).where(m.Device.fcm_token.in_(list(tokens))))
        await db.flush()
