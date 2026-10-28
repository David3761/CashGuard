"""Insert ORM rows with sensible defaults for db/api tests (`await factories.user(db)`).

Not to be confused with `tests/builders.py` (F2, David G.): those build pure domain objects.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m


async def add[T](db: AsyncSession, row: T) -> T:
    db.add(row)
    await db.flush()
    return row


async def user(db: AsyncSession, **kw: Any) -> m.User:
    defaults: dict[str, Any] = {"name": "Test User", "keycloak_sub": str(uuid.uuid4())}
    return await add(db, m.User(**(defaults | kw)))


async def goal(db: AsyncSession, user_id: int, **kw: Any) -> m.Goal:
    defaults: dict[str, Any] = {
        "amount": Decimal("10000.00"),
        "deadline": date(2026, 12, 31),
        "motivation": "Fond de urgență",
    }
    return await add(db, m.Goal(user_id=user_id, **(defaults | kw)))


async def transaction(db: AsyncSession, user_id: int, **kw: Any) -> m.Transaction:
    defaults: dict[str, Any] = {
        "amount": Decimal("500.00"),
        "merchant_raw": "MEGA IMAGE 0451 BUCURESTI",
        "occurred_at": datetime.fromisoformat("2026-06-15T13:05:00+03:00"),
    }
    return await add(db, m.Transaction(user_id=user_id, **(defaults | kw)))
