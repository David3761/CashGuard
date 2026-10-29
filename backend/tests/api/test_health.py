"""F1.1: the app factory and the public liveness route `GET /api/health`."""

import asyncio
import os
import subprocess
import sys

import pytest
from fastapi import FastAPI

import app.main
from app.config import BACKEND_DIR, Settings
from app.main import create_app
from tests.conftest import MakeClient

pytestmark = pytest.mark.api


async def test_health_returns_ok(settings: Settings, make_client: MakeClient) -> None:
    async with make_client(create_app(settings)) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


async def test_health_answers_head_for_probes(settings: Settings, make_client: MakeClient) -> None:
    # Uptime monitors and reverse proxies often probe liveness with HEAD.
    async with make_client(create_app(settings)) as client:
        response = await client.head("/api/health")

    assert response.status_code == 200
    assert response.content == b""


async def test_health_is_only_served_under_the_api_prefix(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(create_app(settings)) as client:
        response = await client.get("/health")

    assert response.status_code == 404


async def test_health_rejects_post(settings: Settings, make_client: MakeClient) -> None:
    async with make_client(create_app(settings)) as client:
        response = await client.post("/api/health")

    assert response.status_code == 405


async def test_health_answers_concurrent_requests_identically(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(create_app(settings)) as client:
        responses = await asyncio.gather(*(client.get("/api/health") for _ in range(50)))

    assert {r.status_code for r in responses} == {200}
    assert all(r.json() == {"status": "ok"} for r in responses)


def test_create_app_returns_independent_apps(settings: Settings) -> None:
    first, second = create_app(settings), create_app(settings)
    first.add_api_route("/only-on-first", lambda: None)

    assert first is not second
    assert "/only-on-first" not in {getattr(route, "path", "") for route in second.routes}


def test_importing_main_creates_no_app() -> None:
    # The app is started with `uvicorn app.main:create_app --factory` (HANDOFFS.md H-2), so
    # importing the module must not build an app as a side effect.
    assert not any(isinstance(value, FastAPI) for value in vars(app.main).values())


def test_importing_main_reads_no_settings() -> None:
    # F1.1 review R8. A fresh interpreter with only invalid settings in its environment: if
    # importing built Settings, the import itself would fail. Nothing else is inherited (no real
    # key, no PYTHONWARNINGS), so only the import decides the result.
    code = "import app.main, app.config; assert app.config.get_settings.cache_info().currsize == 0"
    env = {"PATH": os.environ.get("PATH", ""), "SIM_MODE": "maybe", "MAX_AGENT_ITERATIONS": "0"}
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "ValidationError" not in result.stderr


def test_openapi_documents_health(settings: Settings) -> None:
    schema = create_app(settings).openapi()

    operation = schema["paths"]["/api/health"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert set(schema["paths"]["/api/health"]) == {"get"}
    assert response_schema == {"$ref": "#/components/schemas/Health"}
    assert schema["components"]["schemas"]["Health"]["properties"]["status"]["const"] == "ok"
