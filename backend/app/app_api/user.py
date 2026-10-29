"""The app API's single demo user (`APP_API_USER`), resolved on every request.

`/sim/reset` deletes and re-seeds every user with a new id, so the id is never cached: the
setting names a stable login (`keycloak_sub`), or a numeric users.id for tests and scripts.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db import models as m
from app.errors import DomainError


@dataclass(frozen=True, slots=True)
class AppUser:
    id: int
    sub: str
    language: str


NOT_SET_UP = "The demo account isn't set up yet. Seed the database and try again."


async def resolve_app_user(db: AsyncSession, settings: Settings) -> AppUser:
    """The configured user. Missing → 503 (the server isn't ready), never 404."""
    ref = settings.APP_API_USER
    stmt = select(m.User.id, m.User.keycloak_sub, m.User.language)
    stmt = (
        stmt.where(m.User.id == int(ref))
        if ref.isdigit()
        else stmt.where(m.User.keycloak_sub == ref)
    )
    row = (await db.execute(stmt)).one_or_none()
    if row is None:
        raise DomainError("app_user_missing", NOT_SET_UP, status=503)
    return AppUser(id=row.id, sub=row.keycloak_sub, language=row.language)
