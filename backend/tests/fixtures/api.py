"""API fixtures (F3 step 2).

    async def test_me(client, as_user, db):
        user = await factories.user(db)
        r = await as_user(user).get("/me")      # base URL is http://test/api

`app`: a fresh app whose `get_db` yields the test's `db` session (rolled back after the test)
and whose tokens are checked against the test key. `client`: an httpx client on it.
`as_user(user, roles=(), **token_kw)`: sets `Authorization: Bearer` for that user on `client`.
For code that opens its own sessions (background runs, the pipeline) use `db_committed`.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import JWKSCache
from app.db.session import get_db
from app.main import create_app


@pytest.fixture
def app(db: AsyncSession, test_jwks: JWKSCache) -> Iterator[FastAPI]:
    application = create_app()

    async def test_db() -> AsyncIterator[AsyncSession]:
        yield db

    application.dependency_overrides[get_db] = test_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as c:
        yield c


def subject(user: Any) -> str:
    """A Keycloak `sub`: from a users row (anything with `keycloak_sub`) or a str."""
    return user if isinstance(user, str) else str(user.keycloak_sub)


@pytest.fixture
def as_user(
    client: httpx.AsyncClient, make_token: Callable[..., str]
) -> Callable[..., httpx.AsyncClient]:
    def _as(user: Any, roles: tuple[str, ...] = (), **token_kw: Any) -> httpx.AsyncClient:
        token = make_token(sub=subject(user), roles=roles, **token_kw)
        client.headers["Authorization"] = f"Bearer {token}"
        return client

    return _as


@pytest.fixture
async def committed_client(
    db_committed: AsyncSession, test_jwks: JWKSCache
) -> AsyncIterator[httpx.AsyncClient]:
    """An app on committed data: endpoints and background tasks see the same rows."""
    transport = httpx.ASGITransport(app=create_app(), raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as c:
        yield c


@pytest.fixture
def as_committed_user(
    committed_client: httpx.AsyncClient, make_token: Callable[..., str]
) -> Callable[..., httpx.AsyncClient]:
    def _as(user: Any, roles: tuple[str, ...] = (), **token_kw: Any) -> httpx.AsyncClient:
        token = make_token(sub=subject(user), roles=roles, **token_kw)
        committed_client.headers["Authorization"] = f"Bearer {token}"
        return committed_client

    return _as
