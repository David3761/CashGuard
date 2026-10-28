"""Database fixtures (F3 step 1, started early for B2).

`engine`: one per test session on TEST_DATABASE_URL, schema dropped and recreated once.
`db`: a session inside an outer transaction that is rolled back after the test; the session
itself runs in a SAVEPOINT, so `commit()` / `rollback()` inside a test stay contained.
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import get_settings
from app.db.init import create_all, drop_all


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(get_settings().TEST_DATABASE_URL)
    async with eng.begin() as conn:
        await drop_all(conn)
        await create_all(conn)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        outer = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await outer.rollback()
