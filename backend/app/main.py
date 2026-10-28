from fastapi import APIRouter, FastAPI

from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.logging import configure_logging


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

    app.include_router(api)
    return app


app = create_app()
