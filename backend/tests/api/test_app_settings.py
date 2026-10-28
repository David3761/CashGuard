"""F1.2: `create_app(settings)` stores the settings; routes read them with `get_app_settings`."""

from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Depends, FastAPI

from app.config import Settings, get_app_settings
from app.main import create_app
from tests.conftest import MakeClient

pytestmark = pytest.mark.api


def _add_model_route(application: FastAPI) -> None:
    @application.get("/model")
    async def model(settings: Annotated[Settings, Depends(get_app_settings)]) -> dict[str, str]:
        return {"model": settings.ANTHROPIC_MODEL}


def test_create_app_stores_the_given_settings(settings: Settings) -> None:
    assert create_app(settings).state.settings is settings


def test_create_app_without_settings_uses_get_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SIM_MODE=true\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)

    application = create_app()

    assert isinstance(application.state.settings, Settings)
    assert application.state.settings.SIM_MODE is True


async def test_routes_read_the_app_settings(make_client: MakeClient) -> None:
    application = create_app(Settings(_env_file=None, ANTHROPIC_MODEL="claude-opus-5-5"))
    _add_model_route(application)

    async with make_client(application) as client:
        response = await client.get("/model")

    assert response.json() == {"model": "claude-opus-5-5"}


async def test_get_app_settings_fails_loudly_on_an_app_not_built_by_create_app(
    make_client: MakeClient,
) -> None:
    application = FastAPI()
    _add_model_route(application)

    async with make_client(application) as client:
        with pytest.raises(RuntimeError, match="create_app"):
            await client.get("/model")
