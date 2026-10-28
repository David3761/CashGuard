import httpx
import pytest
from pydantic import BaseModel

from app.errors import DomainError
from app.main import create_app


class Body(BaseModel):
    amount: int


@pytest.fixture
def app():
    app = create_app()

    @app.get("/api/_test/domain-error")
    async def raise_domain_error() -> None:
        raise DomainError("x_code", "Something specific went wrong.", status=409)

    @app.get("/api/_test/crash")
    async def crash() -> None:
        raise RuntimeError("secret internal detail")

    @app.post("/api/_test/body")
    async def body(payload: Body) -> dict[str, int]:
        return {"amount": payload.amount}

    return app


@pytest.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_returns_ok(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_unknown_route_returns_404_envelope(client):
    r = await client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


async def test_domain_error_returns_its_status_and_envelope(client):
    r = await client.get("/api/_test/domain-error")
    assert r.status_code == 409
    assert r.json() == {"error": {"code": "x_code", "message": "Something specific went wrong."}}


async def test_bad_body_returns_422_envelope(client):
    r = await client.post("/api/_test/body", json={"amount": "lots"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "invalid_request"
    assert "amount" in err["message"]


async def test_unexpected_error_returns_500_without_stack_trace(client):
    r = await client.get("/api/_test/crash")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret internal detail" not in r.text
    assert "Traceback" not in r.text
