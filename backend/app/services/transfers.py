"""Transfers to savings: manual and the payday auto-save (D37) (B3 step 2)."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import TransferKind
from app.errors import DomainError
from app.services._common import as_enum, invalid, owned, unique_or, view


async def get(db: AsyncSession, user_id: int, transfer_id: int) -> dm.Transfer:
    """One transfer. Another user's → not_found."""
    return view(dm.Transfer, await owned(db, m.Transfer, user_id, transfer_id, "Transfer"))


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    amount: Decimal,
    kind: TransferKind = TransferKind.MANUAL,
    pot_id: int | None = None,
    income_transaction_id: int | None = None,
) -> dm.Transfer:
    """Record the transfer (moving the money is the engine's job). A second auto-save for the
    same income transaction → already_saved (409)."""
    if amount <= 0:
        raise invalid("invalid_amount", "A transfer amount must be positive.")
    row = m.Transfer(
        user_id=user_id,
        amount=amount,
        kind=as_enum(TransferKind, kind, "invalid_transfer_kind"),
        pot_id=pot_id,
        income_transaction_id=income_transaction_id,
    )

    async def insert() -> m.Transfer:
        db.add(row)
        await db.flush()
        return row

    already = DomainError("already_saved", "This salary was already auto-saved.", status=409)
    return view(dm.Transfer, await unique_or(db, insert, already))


async def for_income(
    db: AsyncSession, user_id: int, income_transaction_id: int
) -> dm.Transfer | None:
    """The auto-save made for that salary, if any (idempotency check)."""
    row = await db.scalar(
        select(m.Transfer).where(
            m.Transfer.user_id == user_id,
            m.Transfer.income_transaction_id == income_transaction_id,
            m.Transfer.kind == TransferKind.AUTO_SAVE,
        )
    )
    return view(dm.Transfer, row) if row is not None else None


async def undo(db: AsyncSession, user_id: int, transfer_id: int) -> dm.Transfer:
    """Set `undone_at` once; a second undo → already_undone (409). The caller moves the money
    back."""
    row = await owned(db, m.Transfer, user_id, transfer_id, "Transfer")
    if row.undone_at is not None:
        raise DomainError("already_undone", "This transfer was already undone.", status=409)
    row.undone_at = clock.now()
    await db.flush()
    return view(dm.Transfer, row)
