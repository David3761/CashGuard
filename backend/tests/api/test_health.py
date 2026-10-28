"""F1.1: the app factory and the public liveness route `GET /api/health`."""

import asyncio

import httpx
import pytest
from fastapi import FastAPI

import app.main
from app.main import create_app

pytestmark = pytest.mark.api


def _client(application: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url="http://test")


async def test_health_returns_ok() -> None:
    async with _client(create_app()) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["content-type"] == "application/json"


async def test_health_answers_head_for_probes() -> None:
    # Uptime monitors and reverse proxies often probe liveness with HEAD.
    async with _client(create_app()) as client:
        response = await client.head("/api/health")

    assert response.status_code == 200
    assert response.content == b""


async def test_health_is_only_served_under_the_api_prefix() -> None:
    async with _client(create_app()) as client:
        response = await client.get("/health")

    assert response.status_code == 404


async def test_health_rejects_post() -> None:
    async with _client(create_app()) as client:
        response = await client.post("/api/health")

    assert response.status_code == 405


async def test_health_answers_concurrent_requests_identically() -> None:
    async with _client(create_app()) as client:
        responses = await asyncio.gather(*(client.get("/api/health") for _ in range(50)))

    assert {r.status_code for r in responses} == {200}
    assert all(r.json() == {"status": "ok"} for r in responses)


def test_create_app_returns_independent_apps() -> None:
    first, second = create_app(), create_app()
    first.add_api_route("/only-on-first", lambda: None)

    assert first is not second
    assert "/only-on-first" not in {getattr(route, "path", "") for route in second.routes}


def test_importing_main_creates_no_app() -> None:
    # The app is started with `uvicorn app.main:create_app --factory` (HANDOFFS.md H-2), so
    # importing the module must not build an app as a side effect.
    assert not any(isinstance(value, FastAPI) for value in vars(app.main).values())


def test_openapi_documents_health() -> None:
    schema = create_app().openapi()

    operation = schema["paths"]["/api/health"]["get"]
    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert set(schema["paths"]["/api/health"]) == {"get"}
    assert response_schema == {"$ref": "#/components/schemas/Health"}
    assert schema["components"]["schemas"]["Health"]["properties"]["status"]["const"] == "ok"
