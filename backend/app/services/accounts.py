"""Accounts: the balance and the goal pot mirror (B3 step 1)."""

from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.errors import DomainError
from app.services._common import not_found, unique_or, view


async def get(db: AsyncSession, user_id: int) -> dm.Account:
    """The user's account. Missing → not_found."""
    row = await db.get(m.Account, user_id)
    if row is None:
        raise not_found("Account")
    return view(dm.Account, row)


async def create(
    db: AsyncSession, user_id: int, *, current_balance: Decimal, savings_pot: Decimal = Decimal("0")
) -> dm.Account:
    """The account row (seed, onboarding)."""
    row = m.Account(user_id=user_id, current_balance=current_balance, savings_pot=savings_pot)

    async def insert() -> m.Account:
        db.add(row)
        await db.flush()
        return row

    conflict = DomainError("conflict", "The account already exists.", status=409)
    return view(dm.Account, await unique_or(db, insert, conflict))


async def adjust_balance(db: AsyncSession, user_id: int, delta: Decimal) -> dm.Account:
    """balance += delta (negative for debits), atomically in SQL. The balance may go negative."""
    result = await db.execute(
        update(m.Account)
        .where(m.Account.user_id == user_id)
        .values(current_balance=m.Account.current_balance + delta)
        .returning(m.Account.current_balance, m.Account.savings_pot)
        .execution_options(synchronize_session="fetch")
    )
    row = result.one_or_none()
    if row is None:
        raise not_found("Account")
    return dm.Account(current_balance=row.current_balance, savings_pot=row.savings_pot)
