import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app.api import (
    chat,
    context,
    internal,
    me,
    messages,
    notifications,
    plan,
    receivables,
    sim,
    state,
    transactions,
    transfers,
)
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.logging import configure_logging
from app.ws import router as ws_router

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    """SIM_MODE: the app clock is the simulator's (date from the sim_clock table)."""
    from app import clock
    from app.db.session import unit_of_work
    from app.sim.clock_store import SimClock

    start = get_settings().SIM_START_DATE
    sim = SimClock(start)
    try:
        async with unit_of_work() as db:
            await sim.load(db, start)
    except Exception:
        log.warning("sim clock: DB not reachable, starting at %s", start)
    clock.set_clock(sim)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
        lifespan=_lifespan if settings.SIM_MODE and settings.SIM_CLOCK_FROM_DB else None,
        title="CashGuard API",
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    install_error_handlers(app)

    api = APIRouter(prefix="/api")

    @api.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    api.include_router(internal.router)
    for module in (
        chat,
        me,
        state,
        messages,
        notifications,
        plan,
        transactions,
        transfers,
        receivables,
        context,
    ):
        api.include_router(module.router)
    if settings.SIM_MODE:
        api.include_router(sim.router)
    app.include_router(api)
    app.include_router(ws_router)
    return app


app = create_app()
