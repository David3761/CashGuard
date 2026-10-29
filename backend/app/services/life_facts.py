"""Life facts: the person's life, one row per statement (arch 5.3) (B3 step 4).

States: hypothesis → confirmed | rejected; confirmed → expired. A rejected fact is never
proposed again (the inference checks rejected ones too).
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import local_date
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import FactStatus, Persistence
from app.services._common import invalid, invalid_transition, owned

CONFIRMED_CONFIDENCE = Decimal("0.9")


def _view(row: m.LifeFact) -> dm.LifeFact:
    return dm.LifeFact.model_validate(
        {
            "id": row.id,
            "type": row.type,
            "value": row.value,
            # The columns allow NULL; our LifeFact doesn't: a fact without its own words shows
            # its type, one without a start date is valid since it was recorded.
            "text": row.text or str(row.type),
            "source": row.source,
            "status": row.status,
            "confidence": float(row.confidence),
            "persistence": row.persistence,
            "valid_from": row.valid_from or local_date(row.created_at),
            "valid_to": row.valid_to,
            "evidence": row.evidence or {},
            "created_at": row.created_at,
        }
    )


def _validated(**fields: Any) -> dm.LifeFact:
    try:
        return dm.LifeFact.model_validate(fields)
    except ValidationError as exc:
        raise invalid("invalid_fact", str(exc.errors()[0]["msg"])) from exc


def _write(row: m.LifeFact, fact: dm.LifeFactDraft) -> None:
    row.type = fact.type
    row.value = fact.value.model_dump(mode="json")  # JSON only where the column is JSONB
    row.text = fact.text
    row.source = fact.source
    row.status = fact.status
    row.confidence = Decimal(str(fact.confidence))
    row.persistence = fact.persistence
    row.valid_from = fact.valid_from
    row.valid_to = fact.valid_to
    row.evidence = fact.model_dump(mode="json")["evidence"]


async def _row(db: AsyncSession, user_id: int, fact_id: int) -> m.LifeFact:
    return await owned(db, m.LifeFact, user_id, fact_id, "Life fact")


async def _move(
    db: AsyncSession, user_id: int, fact_id: int, allowed_from: FactStatus, to: FactStatus
) -> m.LifeFact:
    row = await _row(db, user_id, fact_id)
    if row.status != allowed_from:
        raise invalid_transition("The fact", row.status, to)
    row.status = to
    return row


async def get(db: AsyncSession, user_id: int, fact_id: int) -> dm.LifeFact:
    """One fact. Another user's → not_found."""
    return _view(await _row(db, user_id, fact_id))


async def create(db: AsyncSession, user_id: int, fact: dm.LifeFactDraft) -> dm.LifeFact:
    """Store a validated fact (a `LifeFactDraft`; a LifeFact's `id` is ignored); returns it
    with the new id."""
    row = m.LifeFact(user_id=user_id)
    _write(row, fact)
    db.add(row)
    await db.flush()
    return _view(row)


async def update(
    db: AsyncSession,
    user_id: int,
    fact_id: int,
    *,
    value: dict[str, Any] | None = None,
    text: str | None = None,
    persistence: Persistence | None = None,
    valid_from: date | None = None,
    valid_to: date | None = None,
    confidence: float | None = None,
) -> dm.LifeFact:
    """Change only the fields given; the result is re-validated (F2 rules)."""
    row = await _row(db, user_id, fact_id)
    current = _view(row).model_dump()
    changes = {
        "value": value,
        "text": text,
        "persistence": persistence,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "confidence": confidence,
    }
    fact = _validated(**(current | {k: v for k, v in changes.items() if v is not None}))
    _write(row, fact)
    await db.flush()
    return _view(row)


async def expire(db: AsyncSession, user_id: int, fact_id: int, valid_to: date) -> dm.LifeFact:
    """confirmed → expired from `valid_to`. Otherwise → invalid_transition."""
    row = await _move(db, user_id, fact_id, FactStatus.CONFIRMED, FactStatus.EXPIRED)
    if row.valid_from is not None and valid_to < row.valid_from:
        raise invalid("invalid_fact", "valid_to must be on or after valid_from.")
    row.valid_to = valid_to
    await db.flush()
    return _view(row)


async def delete(db: AsyncSession, user_id: int, fact_id: int) -> None:
    """Remove the fact and its signatures (cascade). Another user's → not_found."""
    await db.delete(await _row(db, user_id, fact_id))
    await db.flush()


async def list_all(
    db: AsyncSession, user_id: int, status: FactStatus | None = None
) -> Sequence[dm.LifeFact]:
    """Every fact, or only one status (GET /life-facts?status=)."""
    stmt = select(m.LifeFact).where(m.LifeFact.user_id == user_id)
    if status is not None:
        stmt = stmt.where(m.LifeFact.status == status)
    return [_view(r) for r in await db.scalars(stmt.order_by(m.LifeFact.id))]


async def list_active(db: AsyncSession, user_id: int, on_date: date) -> Sequence[dm.LifeFact]:
    """Confirmed facts whose validity window contains `on_date` (inclusive)."""
    rows = await db.scalars(
        select(m.LifeFact)
        .where(
            m.LifeFact.user_id == user_id,
            m.LifeFact.status == FactStatus.CONFIRMED,
            or_(m.LifeFact.valid_from.is_(None), m.LifeFact.valid_from <= on_date),
            or_(m.LifeFact.valid_to.is_(None), m.LifeFact.valid_to >= on_date),
        )
        .order_by(m.LifeFact.id)
    )
    return [_view(r) for r in rows]


async def list_hypotheses(db: AsyncSession, user_id: int) -> Sequence[dm.LifeFact]:
    """Facts still waiting for the 1-tap confirmation."""
    return await list_all(db, user_id, FactStatus.HYPOTHESIS)


async def confirm(db: AsyncSession, user_id: int, fact_id: int) -> dm.LifeFact:
    """hypothesis → confirmed (confidence 0.9). Otherwise → invalid_transition."""
    row = await _move(db, user_id, fact_id, FactStatus.HYPOTHESIS, FactStatus.CONFIRMED)
    row.confidence = max(row.confidence, CONFIRMED_CONFIDENCE)
    await db.flush()
    return _view(row)


async def reject(db: AsyncSession, user_id: int, fact_id: int) -> dm.LifeFact:
    """hypothesis → rejected (kept: never proposed again). Otherwise → invalid_transition."""
    row = await _move(db, user_id, fact_id, FactStatus.HYPOTHESIS, FactStatus.REJECTED)
    await db.flush()
    return _view(row)
