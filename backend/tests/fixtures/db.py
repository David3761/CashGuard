"""Database fixtures (F3 step 1, started early for B2).

`engine`: one per test session on TEST_DATABASE_URL; tables dropped, then rebuilt with the
Alembic migrations (`upgrade head`), so every test runs on the migrated schema.
`db`: a session inside an outer transaction that is rolled back after the test; the session
itself runs in a SAVEPOINT, so `commit()` / `rollback()` inside a test stay contained.
`db_committed`: real commits (pipeline, locks, background runs, concurrency); the app's own
sessions (`unit_of_work()`, `get_db()`) use the test DB too; every table is truncated after.
"""

from collections.abc import AsyncIterator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from app.config import get_settings
from app.db import session as app_session
from app.db.init import drop_all, upgrade
from app.db.models import Base


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


@pytest.fixture
async def db_committed(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    app_session.use_engine(engine)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session
    finally:
        app_session.use_engine(None)
        tables = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
        async with engine.begin() as conn:
            await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
