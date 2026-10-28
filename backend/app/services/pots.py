"""Named savings pots; the goal has its own (arch 4.4) (B3 step 4)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm
from app.domain.enums import PotKind


async def get(db: AsyncSession, user_id: int, pot_id: int) -> dm.Pot:
    """One pot. Another user's → not_found."""
    raise NotImplementedError("B3 step 4")


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    name: str,
    kind: PotKind,
    target: Decimal,
    deadline: date | None = None,
    goal_id: int | None = None,
    life_event_id: int | None = None,
    fact_id: int | None = None,
    monthly_contribution: Decimal = Decimal("0"),
) -> dm.Pot:
    """An active pot (saved 0)."""
    raise NotImplementedError("B3 step 4")


async def update(
    db: AsyncSession,
    user_id: int,
    pot_id: int,
    *,
    name: str | None = None,
    target: Decimal | None = None,
    deadline: date | None = None,
    monthly_contribution: Decimal | None = None,
) -> dm.Pot:
    """Change only the fields given. A closed pot → invalid_transition."""
    raise NotImplementedError("B3 step 4")


async def close(db: AsyncSession, user_id: int, pot_id: int) -> dm.Pot:
    """active | completed → closed. Already closed → invalid_transition."""
    raise NotImplementedError("B3 step 4")


async def list_active(db: AsyncSession, user_id: int) -> Sequence[dm.Pot]:
    """Active pots, the goal pot first."""
    raise NotImplementedError("B3 step 4")


async def goal_pot(db: AsyncSession, user_id: int) -> dm.Pot | None:
    """The active goal's pot, or None."""
    raise NotImplementedError("B3 step 4")


async def add_saved(db: AsyncSession, user_id: int, pot_id: int, delta: Decimal) -> dm.Pot:
    """saved += delta atomically (negative when a pot pays for something). Below 0 →
    insufficient_pot_balance (409). Keeps `accounts.savings_pot` equal to the goal pot."""
    raise NotImplementedError("B3 step 4")
