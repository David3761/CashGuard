"""The app factory. Run with `uvicorn app.main:create_app --factory --workers 1`."""

from typing import Literal

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel
from starlette.types import ASGIApp

from app.config import Settings, get_settings
from app.errors import ERROR_RESPONSES, install_error_handlers, outermost_first


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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build a new app. No module-level instance, so importing has no side effects.

    `settings` defaults to `get_settings()` (env + backend/.env); tests pass their own. Routes read
    them with `Depends(app.config.get_app_settings)`.
    """
    settings = get_settings() if settings is None else settings
    # Every route documents the arch 9.1 error envelope (instead of FastAPI's own 422 shape).
    app = _App(title="CashGuard API", version="0.1.0", responses=ERROR_RESPONSES)
    app.state.settings = settings
    install_error_handlers(app)
    api = APIRouter(prefix="/api")
    api.include_router(_health_router())
    app.include_router(api)
    return app
