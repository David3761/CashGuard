"""Schema management with Alembic (migrations in `backend/migrations/`).

    uv run python -m app.db.init            # = alembic upgrade head on DATABASE_URL
    uv run python -m app.db.init --reset    # drop every table first (deletes all data)

Code (tests, the seed loader) calls `upgrade(conn)` / `downgrade(conn)` / `drop_all(conn)` on an
open connection; Alembic then runs inside that connection's transaction.
"""

import argparse
import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.config import get_settings
from app.db.models import Base

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def alembic_config(connection: Connection | None = None) -> Config:
    cfg = Config(str(ALEMBIC_INI))
    if connection is not None:
        cfg.attributes["connection"] = connection
    return cfg


async def upgrade(conn: AsyncConnection, revision: str = "head") -> None:
    await conn.run_sync(lambda sync: command.upgrade(alembic_config(sync), revision))


async def downgrade(conn: AsyncConnection, revision: str = "base") -> None:
    await conn.run_sync(lambda sync: command.downgrade(alembic_config(sync), revision))


async def drop_all(conn: AsyncConnection) -> None:
    # DROP … CASCADE rather than metadata.drop_all / downgrade: it works whatever shape the
    # existing tables have (an older schema, a half-applied migration).
    names = [t.name for t in reversed(Base.metadata.sorted_tables)] + ["alembic_version"]
    for name in names:
        await conn.execute(text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))


async def _main(reset: bool) -> None:
    engine = create_async_engine(get_settings().DATABASE_URL)
    async with engine.begin() as conn:
        if reset:
            await drop_all(conn)
        await upgrade(conn)
    await engine.dispose()
    print(f"{'reset and ' if reset else ''}migrated to head ({len(Base.metadata.tables)} tables)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    asyncio.run(_main(parser.parse_args().reset))
