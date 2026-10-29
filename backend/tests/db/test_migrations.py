"""Alembic migrations: they build exactly the models' schema, round-trip, and have one head."""

from enum import StrEnum

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db import models as m
from app.db.init import alembic_config, downgrade, drop_all, upgrade
from app.db.migration_helpers import replace_enum_check

OUR_TABLES = text(
    "select count(*) from information_schema.tables "
    "where table_schema = current_schema() and table_name <> 'alembic_version'"
)


def test_migrations_have_a_single_head():
    # Two teammates adding migrations in parallel create two heads: merge them before pushing.
    heads = ScriptDirectory.from_config(alembic_config()).get_heads()
    assert len(heads) == 1, f"multiple heads {heads}: run `uv run alembic merge heads`"


async def test_migrated_schema_matches_the_models(engine):
    # Fails when a model changed without a migration: `uv run alembic revision --autogenerate`.
    async with engine.connect() as conn:
        diff = await conn.run_sync(
            lambda sync: compare_metadata(
                MigrationContext.configure(sync, opts={"compare_type": True}), m.Base.metadata
            )
        )
    assert diff == []


async def test_upgrade_downgrade_round_trip_in_a_scratch_schema(engine):
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("CREATE SCHEMA b2_scratch"))
        await conn.execute(text("SET LOCAL search_path TO b2_scratch"))
        await upgrade(conn)
        assert await conn.scalar(OUR_TABLES) == len(m.Base.metadata.tables)
        await downgrade(conn)
        assert await conn.scalar(OUR_TABLES) == 0
        await upgrade(conn)
        assert await conn.scalar(OUR_TABLES) == len(m.Base.metadata.tables)
        await trans.rollback()


async def test_replace_enum_check_lets_a_new_enum_value_in(engine):
    # Autogenerate doesn't see CHECK changes: adding an enum value needs this helper in a migration.
    class LanguagePlus(StrEnum):
        RO = "ro"
        EN = "en"
        DE = "de"

    insert = text(
        "INSERT INTO users (keycloak_sub, name, language, coach_style, timezone, "
        "household_scale, created_at) VALUES (:sub, 'x', 'de', 'warm', 'UTC', 1, now())"
    )
    async with engine.connect() as conn:
        trans = await conn.begin()
        with pytest.raises(IntegrityError):
            async with conn.begin_nested():
                await conn.execute(insert, {"sub": "before"})

        def migrate(sync_conn):
            with Operations.context(MigrationContext.configure(sync_conn)):
                replace_enum_check("users", "language", LanguagePlus)

        await conn.run_sync(migrate)
        await conn.execute(insert, {"sub": "after"})
        await trans.rollback()


async def test_reset_works_on_tables_from_an_older_schema(engine):
    # A reset (drop_all + upgrade) must work whatever shape the old tables have
    # (metadata.drop_all used to fail on a constraint the old schema didn't have).
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("CREATE SCHEMA b2_old"))
        await conn.execute(text("SET LOCAL search_path TO b2_old"))
        await conn.execute(text("CREATE TABLE users (id serial primary key)"))
        await conn.execute(
            text("CREATE TABLE transactions (id serial primary key, user_id int references users)")
        )
        await conn.execute(text("CREATE TABLE alembic_version (version_num varchar(32))"))
        await conn.execute(text("INSERT INTO alembic_version VALUES ('deadbeef')"))
        await drop_all(conn)
        await upgrade(conn)
        assert await conn.scalar(OUR_TABLES) == len(m.Base.metadata.tables)
        await trans.rollback()


async def test_add_goals_soft_keeps_existing_goals_and_makes_them_soft(engine):
    async with engine.connect() as conn:
        trans = await conn.begin()
        await conn.execute(text("CREATE SCHEMA b2_data"))
        await conn.execute(text("SET LOCAL search_path TO b2_data"))
        await upgrade(conn, "71bc35840018")  # the schema before goals.soft
        user_id = await conn.scalar(
            text(
                "INSERT INTO users (keycloak_sub, name, language, coach_style, timezone, "
                "household_scale, created_at) VALUES ('s', 'x', 'ro', 'warm', 'UTC', 1, now()) "
                "RETURNING id"
            )
        )
        await conn.execute(
            text(
                "INSERT INTO goals (user_id, amount, deadline, status, created_at) "
                "VALUES (:u, 10000, '2026-12-31', 'active', now())"
            ),
            {"u": user_id},
        )
        await upgrade(conn)
        assert await conn.scalar(text("SELECT soft FROM goals")) is True
        await trans.rollback()
