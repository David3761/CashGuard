"""Spending signatures: what each fact predicts (arch 5.3.3) (B3 step 4)."""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import FactStatus, SignatureEffect
from app.services._common import owned


def _to_row(user_id: int, fact_id: int, sig: dm.Signature) -> m.SpendingSignature:
    window = sig.time_window.model_dump(mode="json") if sig.time_window else None
    return m.SpendingSignature(
        user_id=user_id,
        fact_id=fact_id,
        effect=sig.effect,
        category=sig.category,
        merchant_hints=list(sig.merchant_hints),
        item_keywords=list(sig.item_keywords),
        amount_min=sig.amount_min,
        amount_max=sig.amount_max,
        multiplier=sig.multiplier,
        time_window=window,
        expected_date=sig.expected_date,
        expected_amount=sig.expected_amount,
        replacement_cycle_days=sig.replacement_cycle_days,
        purpose=sig.purpose,
        strength=Decimal(str(sig.strength)),
        origin=sig.origin,
        active=sig.active,
    )


def _view(row: m.SpendingSignature) -> dm.Signature:
    return dm.Signature.model_validate(
        {
            "id": row.id,
            "fact_id": row.fact_id,
            "effect": row.effect,
            "category": row.category,
            "merchant_hints": row.merchant_hints,
            "item_keywords": row.item_keywords,
            "amount_min": row.amount_min,
            "amount_max": row.amount_max,
            "multiplier": row.multiplier,
            "time_window": row.time_window,
            "expected_date": row.expected_date,
            "expected_amount": row.expected_amount,
            "replacement_cycle_days": row.replacement_cycle_days,
            "purpose": row.purpose,
            "strength": float(row.strength),
            "origin": row.origin,
            "active": row.active,
        }
    )


async def replace_for_fact(
    db: AsyncSession, user_id: int, fact_id: int, signatures: Sequence[dm.Signature]
) -> Sequence[dm.Signature]:
    """Atomically swap the fact's signatures for these (an error halfway keeps the old set).
    Another user's fact → not_found."""
    await owned(db, m.LifeFact, user_id, fact_id, "Life fact")
    async with db.begin_nested():
        await db.execute(delete(m.SpendingSignature).where(m.SpendingSignature.fact_id == fact_id))
        rows = []
        for sig in signatures:
            row = _to_row(user_id, fact_id, sig)
            db.add(row)
            rows.append(row)
        await db.flush()
    return [_view(r) for r in rows]


async def list_active(
    db: AsyncSession, user_id: int, effect: SignatureEffect | None = None
) -> Sequence[dm.Signature]:
    """Active signatures of confirmed facts, optionally of one effect."""
    stmt = (
        select(m.SpendingSignature)
        .join(m.LifeFact, m.LifeFact.id == m.SpendingSignature.fact_id)
        .where(
            m.SpendingSignature.user_id == user_id,
            m.SpendingSignature.active.is_(True),
            m.LifeFact.status == FactStatus.CONFIRMED,
        )
    )
    if effect is not None:
        stmt = stmt.where(m.SpendingSignature.effect == effect)
    rows = await db.scalars(stmt.order_by(m.SpendingSignature.id))
    return [_view(r) for r in rows]


async def list_for_fact(db: AsyncSession, user_id: int, fact_id: int) -> Sequence[dm.Signature]:
    """One fact's signatures (the "Explică: …" line on the profile screen)."""
    await owned(db, m.LifeFact, user_id, fact_id, "Life fact")
    rows = await db.scalars(
        select(m.SpendingSignature)
        .where(m.SpendingSignature.fact_id == fact_id)
        .order_by(m.SpendingSignature.id)
    )
    return [_view(r) for r in rows]
