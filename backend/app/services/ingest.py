"""Ingestion (arch F2, B8 step 1): validate and store; never calls the engine or the AI."""

from datetime import timedelta
from typing import Any

from pydantic import AwareDatetime, Field, ValidationError, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.clock import local_date
from app.db import models as m
from app.domain.base import Frozen, PositiveMoney
from app.domain.enums import Category, Direction, TransactionSource
from app.domain.models import Item
from app.services._common import invalid


class TxIn(Frozen):
    """One incoming transaction (the simulator or a bank feed)."""

    amount: PositiveMoney
    direction: Direction = Direction.DEBIT
    merchant_raw: str = Field(min_length=1, max_length=200)
    occurred_at: AwareDatetime
    mcc: str | None = Field(default=None, max_length=4)
    category: Category | None = None  # the script's category wins over normalisation (Q8)
    items: tuple[Item, ...] | None = None
    description: str | None = None
    source: TransactionSource = TransactionSource.SIM

    @field_validator("occurred_at")
    @classmethod
    def _not_in_the_future(cls, value: AwareDatetime) -> AwareDatetime:
        if local_date(value) > clock.today() + timedelta(days=1):
            raise ValueError("occurred_at is more than a day after the (sim) date")
        return value


async def ingest(db: AsyncSession, user_id: int, tx: TxIn | dict[str, Any]) -> int:
    """Store it as `unresolved` with `effective_amount = amount`; returns the id.
    Invalid → invalid_transaction (422)."""
    try:
        data = tx if isinstance(tx, TxIn) else TxIn.model_validate(tx)
    except ValidationError as exc:
        err = exc.errors()[0]
        where = ".".join(str(p) for p in err["loc"])
        raise invalid("invalid_transaction", f"{where}: {err['msg']}") from exc
    row = m.Transaction(
        user_id=user_id,
        amount=data.amount,
        effective_amount=data.amount,
        direction=data.direction,
        merchant_raw=data.merchant_raw,
        occurred_at=data.occurred_at,
        mcc=data.mcc,
        category=data.category,
        items=[i.model_dump(mode="json") for i in data.items] if data.items else None,
        description=data.description,
        source=data.source,
    )
    db.add(row)
    await db.flush()
    return row.id
