"""The app factory. Run with `uvicorn app.main:create_app --factory --workers 1`."""

from typing import Literal

from fastapi import APIRouter, FastAPI
from pydantic import BaseModel


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


def create_app() -> FastAPI:
    """Build a new app. No module-level instance, so importing has no side effects."""
    app = FastAPI(title="CashGuard API", version="0.1.0")
    api = APIRouter(prefix="/api")
    api.include_router(_health_router())
    app.include_router(api)
    return app
