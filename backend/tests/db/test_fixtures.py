"""F3 step 1: the DB fixtures isolate tests. Tests in this file run in order on purpose."""

from sqlalchemy import func, select, text

from app.db import models as m
from app.db import session as app_session
from tests import factories as f

LEAK_SUB = "f3-leak-check"
COMMITTED_SUB = "f3-committed"


async def count(db, sub: str) -> int:
    return await db.scalar(select(func.count()).where(m.User.keycloak_sub == sub)) or 0


async def test_a_writes_and_even_commits_in_db(db):
    await f.user(db, keycloak_sub=LEAK_SUB)
    await db.commit()  # commits the SAVEPOINT only; the outer transaction is rolled back
    assert await count(db, LEAK_SUB) == 1


async def test_b_does_not_see_test_a_rows(db):
    assert await count(db, LEAK_SUB) == 0


async def test_nested_transaction_rolls_back_inside_a_test(db):
    try:
        async with db.begin_nested():
            await f.user(db, keycloak_sub="f3-nested")
            raise RuntimeError("undo")
    except RuntimeError:
        pass
    assert await count(db, "f3-nested") == 0


async def test_c_db_committed_really_commits(db_committed, engine):
    await f.user(db_committed, keycloak_sub=COMMITTED_SUB)
    await db_committed.commit()
    async with engine.connect() as other:  # another connection sees it
        n = await other.scalar(
            text("select count(*) from users where keycloak_sub = :s"), {"s": COMMITTED_SUB}
        )
    assert n == 1


async def test_d_db_committed_leaves_every_table_empty(db_committed):
    for table in m.Base.metadata.sorted_tables:
        assert await db_committed.scalar(select(func.count()).select_from(table)) == 0, table.name


async def test_db_committed_points_the_app_sessions_at_the_test_db(db_committed):
    # code under test (pipeline, background runs) opens its own sessions with unit_of_work()
    async with app_session.unit_of_work() as own:
        await f.user(own, keycloak_sub="f3-app-session")
    assert await count(db_committed, "f3-app-session") == 1


async def test_db_committed_restarts_ids(db_committed):
    u = await f.user(db_committed)
    await db_committed.commit()
    assert u.id == 1
