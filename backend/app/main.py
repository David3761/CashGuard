from fastapi import APIRouter, FastAPI

from app.api import (
    chat,
    internal,
    me,
    messages,
    notifications,
    plan,
    state,
    transactions,
    transfers,
)
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.logging import configure_logging
from app.ws import router as ws_router


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
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
    for module in (chat, me, state, messages, notifications, plan, transactions, transfers):
        api.include_router(module.router)
    app.include_router(api)
    app.include_router(ws_router)
    return app


app = create_app()
