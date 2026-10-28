"""Create or drop every table (no migrations: the demo DB is reset anyway, work-breakdown 0.1).

uv run python -m app.db.init            # create missing tables in DATABASE_URL
uv run python -m app.db.init --reset    # drop everything first (deletes all data)
"""

import argparse
import asyncio

from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.config import get_settings
from app.db.models import Base


async def create_all(conn: AsyncConnection) -> None:
    await conn.run_sync(Base.metadata.create_all)


async def drop_all(conn: AsyncConnection) -> None:
    await conn.run_sync(Base.metadata.drop_all)


async def _main(reset: bool) -> None:
    engine = create_async_engine(get_settings().DATABASE_URL)
    async with engine.begin() as conn:
        if reset:
            await drop_all(conn)
        await create_all(conn)
    await engine.dispose()
    print(f"{'reset and ' if reset else ''}created {len(Base.metadata.tables)} tables")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="drop all tables first")
    asyncio.run(_main(parser.parse_args().reset))
