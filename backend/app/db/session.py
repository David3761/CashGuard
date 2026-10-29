"""The async engine, the session factory, the FastAPI `get_db` dependency and `unit_of_work()`."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_sessions: async_sessionmaker[AsyncSession] | None = None


def configure(url: str | None = None) -> AsyncEngine:
    """(Re)create the engine; the app uses DATABASE_URL, tests may point it elsewhere."""
    global _engine, _sessions
    _engine = create_async_engine(
        url or get_settings().DATABASE_URL.get_secret_value(), pool_pre_ping=True
    )
    _sessions = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def use_engine(engine: AsyncEngine | None) -> None:
    """Point the app's sessions at an existing engine (tests); None = back to DATABASE_URL."""
    global _engine, _sessions
    _engine = engine
    _sessions = async_sessionmaker(engine, expire_on_commit=False) if engine is not None else None


def get_engine() -> AsyncEngine:
    return _engine if _engine is not None else configure()


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _sessions is None:
        configure()
    assert _sessions is not None
    return _sessions


async def get_db() -> AsyncIterator[AsyncSession]:
    """Request-scoped session. Endpoints commit explicitly."""
    async with session_factory()() as session:
        yield session


@asynccontextmanager
async def unit_of_work() -> AsyncIterator[AsyncSession]:
    """A session that commits on success and rolls back on any exception."""
    async with session_factory()() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
