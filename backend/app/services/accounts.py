"""Accounts: the balance and the goal pot mirror (B3 step 1)."""

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import models as dm


async def get(db: AsyncSession, user_id: int) -> dm.Account:
    """The user's account. Missing → not_found."""
    raise NotImplementedError("B3 step 1")


async def create(
    db: AsyncSession, user_id: int, *, current_balance: Decimal, savings_pot: Decimal = Decimal("0")
) -> dm.Account:
    """The account row (seed, onboarding)."""
    raise NotImplementedError("B3 step 1")


async def adjust_balance(db: AsyncSession, user_id: int, delta: Decimal) -> dm.Account:
    """balance += delta (negative for debits), atomically in SQL. The balance may go negative."""
    raise NotImplementedError("B3 step 1")
