"""Users (B3 step 1)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import CoachStyle, Language
from app.errors import DomainError
from app.services._common import as_enum, invalid, not_found, unique_or, view


async def _row(db: AsyncSession, user_id: int) -> m.User:
    row = await db.get(m.User, user_id)
    if row is None:
        raise not_found("User")
    return row


async def get(db: AsyncSession, user_id: int) -> dm.UserProfile:
    """The user's profile. Unknown id → not_found."""
    return view(dm.UserProfile, await _row(db, user_id))


async def get_by_sub(db: AsyncSession, keycloak_sub: str) -> dm.UserProfile | None:
    """The user for a Keycloak `sub` (auth, B5), or None."""
    row = await db.scalar(select(m.User).where(m.User.keycloak_sub == keycloak_sub))
    return view(dm.UserProfile, row) if row is not None else None


async def create(
    db: AsyncSession,
    *,
    keycloak_sub: str,
    name: str,
    age: int | None = None,
    language: Language = Language.RO,
    city: str | None = None,
) -> dm.UserProfile:
    """A new user (seed, B12). A duplicate `keycloak_sub` → conflict (409)."""
    row = m.User(
        keycloak_sub=keycloak_sub,
        name=name,
        age=age,
        language=as_enum(Language, language, "invalid_language"),
        city=city,
    )

    async def insert() -> m.User:
        db.add(row)
        await db.flush()
        return row

    conflict = DomainError("conflict", "A user with this login already exists.", status=409)
    return view(dm.UserProfile, await unique_or(db, insert, conflict))


async def update(
    db: AsyncSession,
    user_id: int,
    *,
    language: Language | None = None,
    coach_style: CoachStyle | None = None,
    household_scale: Decimal | None = None,
    city: str | None = None,
) -> dm.UserProfile:
    """Change only the fields given (None = unchanged)."""
    row = await _row(db, user_id)
    if language is not None:
        row.language = as_enum(Language, language, "invalid_language")
    if coach_style is not None:
        row.coach_style = as_enum(CoachStyle, coach_style, "invalid_coach_style")
    if household_scale is not None:
        if household_scale < 1:
            raise invalid("invalid_household_scale", "household_scale is at least 1.")
        row.household_scale = household_scale
    if city is not None:
        row.city = city
    await db.flush()
    return view(dm.UserProfile, row)


async def set_onboarded(db: AsyncSession, user_id: int) -> dm.UserProfile:
    """`complete_onboarding`: sets `onboarded_at` to clock.now() (idempotent)."""
    row = await _row(db, user_id)
    if row.onboarded_at is None:
        row.onboarded_at = clock.now()
        await db.flush()
    return view(dm.UserProfile, row)
