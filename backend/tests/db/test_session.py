"""app.db.session: unit_of_work commits or rolls back; get_db yields a working session."""

import pytest
from sqlalchemy import delete, func, select

from app.config import get_settings
from app.db import models as m
from app.db import session as s


@pytest.fixture
async def real_sessions(engine):
    """The app's session factory on the test DB, with real commits cleaned up after."""
    s.configure(get_settings().TEST_DATABASE_URL)
    yield
    async with engine.begin() as conn:
        await conn.execute(delete(m.User).where(m.User.keycloak_sub.like("uow-%")))
    await s.get_engine().dispose()
    s._engine = s._sessions = None


async def count_users(sub: str) -> int:
    async with s.session_factory()() as other:
        return await other.scalar(select(func.count()).where(m.User.keycloak_sub == sub)) or 0


async def test_unit_of_work_commits_on_success(real_sessions):
    async with s.unit_of_work() as db:
        db.add(m.User(name="A", keycloak_sub="uow-ok"))
    assert await count_users("uow-ok") == 1


async def test_unit_of_work_rolls_back_on_exception(real_sessions):
    with pytest.raises(RuntimeError):
        async with s.unit_of_work() as db:
            db.add(m.User(name="B", keycloak_sub="uow-fail"))
            await db.flush()
            raise RuntimeError("boom")
    assert await count_users("uow-fail") == 0


async def test_get_db_yields_a_usable_session(real_sessions):
    agen = s.get_db()
    db = await anext(agen)
    assert await db.scalar(select(1)) == 1
    await agen.aclose()
