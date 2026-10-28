"""F3 step 2: the API fixtures (client, as_user, the test DB session, the test key)."""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.db import models as m
from app.db.session import get_db
from tests import factories as f


def add_test_routes(app):
    @app.get("/api/_test/whoami")
    async def whoami(authorization: str = Header()) -> dict[str, object]:
        claims = await verify_token(authorization.removeprefix("Bearer "))
        return {"sub": claims.sub, "roles": sorted(claims.roles)}

    @app.get("/api/_test/users/{sub}")
    async def user_exists(sub: str, db: Annotated[AsyncSession, Depends(get_db)]) -> dict[str, int]:
        n = await db.scalar(select(func.count()).where(m.User.keycloak_sub == sub))
        return {"count": n or 0}


async def test_client_base_url_is_the_api_prefix(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


async def test_as_user_sends_a_token_for_that_user(app, as_user, db):
    add_test_routes(app)
    user = await f.user(db)
    r = await as_user(user).get("/_test/whoami")
    assert r.status_code == 200
    assert r.json()["sub"] == user.keycloak_sub


async def test_as_user_with_roles_and_a_plain_sub(app, as_user):
    add_test_routes(app)
    r = await as_user("cron-sa", roles=("internal",)).get("/_test/whoami")
    assert r.json() == {"sub": "cron-sa", "roles": ["default-roles-cashguard", "internal"]}


async def test_as_user_can_make_an_expired_token(app, as_user):
    add_test_routes(app)
    r = await as_user("someone", exp_in=-31).get("/_test/whoami")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "token_expired"


async def test_app_reads_the_tests_own_db_session(app, client, db):
    add_test_routes(app)
    user = await f.user(db)  # not committed: only visible through the same session
    r = await client.get(f"/_test/users/{user.keycloak_sub}")
    assert r.json() == {"count": 1}
