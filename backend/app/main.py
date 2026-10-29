"""The app factory. Run with `uvicorn app.main:create_app --factory --workers 1`."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Literal

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from starlette.types import ASGIApp

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
from app.errors import ERROR_RESPONSES, install_error_handlers, outermost_first
from app.logging import configure_logging
from app.ws import router as ws_router

logger = logging.getLogger(__name__)


class _App(FastAPI):
    """FastAPI, with the error middleware kept outermost among the user middleware, so that a
    DomainError raised in any middleware (also one added after create_app) gets its status."""

    def build_middleware_stack(self) -> ASGIApp:
        self.user_middleware = outermost_first(self.user_middleware)
        return super().build_middleware_stack()


class Health(BaseModel):
    status: Literal["ok"]


def _health_router() -> APIRouter:
    router = APIRouter()

    # HEAD for uptime monitors and proxies; kept out of the schema (one operation id per route).
    @router.get("/health")
    @router.head("/health", include_in_schema=False)
    async def health() -> Health:
        """Liveness probe. The only /api route that needs no token."""
        return Health(status="ok")

    return router


def _lifespan(settings: Settings) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Startup: wire the agent to the platform (D42), and in SIM_MODE install the simulator's
    clock (date from the sim_clock table; bomboe B10). In-process test clients don't run it."""

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        from app.agent import platform

        platform.install()
        if settings.SIM_MODE and settings.SIM_CLOCK_FROM_DB:
            from app import clock
            from app.db.session import unit_of_work
            from app.sim.clock_store import SimClock

            start = settings.SIM_START_DATE
            sim_clock = SimClock(start)
            try:
                async with unit_of_work() as db:
                    await sim_clock.load(db, start)
            except Exception:  # the DB may be down at startup; the sim then starts at the start
                logger.warning("sim clock: DB not reachable, starting at %s", start)
            clock.set_clock(sim_clock)
        yield

    return lifespan


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a new app. No module-level instance, so importing has no side effects.

    `settings` defaults to `get_settings()` (env + backend/.env); tests pass their own. Routes read
    them with `Depends(app.config.get_app_settings)`.
    """
    settings = get_settings() if settings is None else settings
    configure_logging(settings.LOG_LEVEL)
    # Every route documents the arch 9.1 error envelope (instead of FastAPI's own 422 shape).
    app = _App(
        title="CashGuard API",
        version="0.1.0",
        responses=ERROR_RESPONSES,
        lifespan=_lifespan(settings),
        openapi_url="/api/openapi.json",
        docs_url="/api/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    install_error_handlers(app)
    api = APIRouter(prefix="/api")
    api.include_router(_health_router())
    # bomboe's platform routers (B6a/B6b/B8/B9/B10/B11).
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
    if settings.APP_API_ENABLED:  # David V.'s Flutter contract at the root (API_SPEC.md)
        from app.app_api.router import install_app_api

        install_app_api(app, settings)
    # Secrets show as "**********" (SecretStr) and the redaction filter backs that up.
    logger.info("app_configured", extra={"settings": settings.model_dump(mode="json")})
    return app
