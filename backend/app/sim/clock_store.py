"""The simulator's clock (B10): the sim date lives in `sim_clock`; the time of day is real
Bucharest time, so timestamps keep moving within a sim day."""

from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import BUCHAREST
from app.db import models as m


class SimClock:
    def __init__(self, today: date) -> None:
        self._today = today

    def today(self) -> date:
        return self._today

    def now(self) -> datetime:
        real = datetime.now(BUCHAREST)  # only the time of day; the date is the sim's
        return datetime.combine(self._today, real.timetz())

    async def load(self, db: AsyncSession, default: date) -> date:
        stored = await db.scalar(select(m.SimClock.today).where(m.SimClock.id == 1))
        self._today = stored or default
        return self._today

    async def set(self, db: AsyncSession, day: date) -> date:
        await db.merge(m.SimClock(id=1, today=day))
        await db.flush()
        self._today = day
        return day

    async def advance(self, db: AsyncSession, days: int = 1) -> date:
        return await self.set(db, self._today + timedelta(days=days))
