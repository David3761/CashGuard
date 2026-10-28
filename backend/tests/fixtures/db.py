"""Database fixtures (F3 step 1, started early for B2).

`engine`: one per test session on TEST_DATABASE_URL; tables dropped, then rebuilt with the
Alembic migrations (`upgrade head`), so every test runs on the migrated schema.
`db`: a session inside an outer transaction that is rolled back after the test; the session
itself runs in a SAVEPOINT, so `commit()` / `rollback()` inside a test stay contained.
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import get_settings
from app.db.init import drop_all, upgrade


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(get_settings().TEST_DATABASE_URL)
    async with eng.begin() as conn:
        await drop_all(conn)
        await upgrade(conn)
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
