"""Users (B3 step 1)."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import CoachStyle, Language


async def get(db: AsyncSession, user_id: int) -> dm.UserProfile:
    """The user's profile. Unknown id → not_found."""
    raise NotImplementedError("B3 step 1")


async def get_by_sub(db: AsyncSession, keycloak_sub: str) -> dm.UserProfile | None:
    """The user for a Keycloak `sub` (auth, B5), or None."""
    raise NotImplementedError("B3 step 1")


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
    raise NotImplementedError("B3 step 1")


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
    raise NotImplementedError("B3 step 1")


async def set_onboarded(db: AsyncSession, user_id: int) -> dm.UserProfile:
    """`complete_onboarding`: sets `onboarded_at` to clock.now() (idempotent)."""
    raise NotImplementedError("B3 step 1")
