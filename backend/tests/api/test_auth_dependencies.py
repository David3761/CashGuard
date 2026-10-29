"""B5 step 2: current_user, require_internal, require_sim, ws_user."""

from typing import Annotated

import pytest
from fastapi import Depends

from app.auth import Claims, current_user, require_internal, require_sim
from app.domain.models import UserProfile
from tests import factories as f


@pytest.fixture
def routes(app):
    @app.get("/api/_test/me")
    async def me(user: Annotated[UserProfile, Depends(current_user)]) -> dict[str, int]:
        return {"id": user.id}

    @app.post("/api/_test/internal")
    async def internal(claims: Annotated[Claims, Depends(require_internal)]) -> dict[str, str]:
        return {"azp": claims.azp or ""}

    @app.post("/api/_test/sim")
    async def sim(claims: Annotated[Claims, Depends(require_sim)]) -> dict[str, str]:
        return {"sub": claims.sub}

    return app


async def code(r) -> str:
    return r.json()["error"]["code"]


async def test_current_user_resolves_the_sub(routes, as_user, db):
    u = await f.user(db)
    r = await as_user(u).get("/_test/me")
    assert r.status_code == 200 and r.json() == {"id": u.id}


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "Basic abc", "token"])
async def test_missing_token(routes, client, header):
    headers = {} if header is None else {"Authorization": header}
    r = await client.get("/_test/me", headers=headers)
    assert r.status_code == 401 and await code(r) == "missing_token"


async def test_lowercase_bearer_is_accepted(routes, client, make_token, db):
    u = await f.user(db)
    r = await client.get(
        "/_test/me", headers={"Authorization": f"bearer {make_token(sub=u.keycloak_sub)}"}
    )
    assert r.status_code == 200


async def test_valid_token_for_an_unknown_user(routes, as_user):
    r = await as_user("not-in-the-db").get("/_test/me")
    assert r.status_code == 401 and await code(r) == "unknown_user"


async def test_bad_token_is_401(routes, client):
    r = await client.get("/_test/me", headers={"Authorization": "Bearer garbage"})
    assert r.status_code == 401 and await code(r) == "invalid_token"


async def test_internal_needs_the_role(routes, as_user, db):
    u = await f.user(db)
    r = await as_user(u).post("/_test/internal")
    assert r.status_code == 403 and await code(r) == "forbidden"
    r = await as_user("cron-sa", roles=("internal",), azp="savings-cron").post("/_test/internal")
    assert r.status_code == 200 and r.json() == {"azp": "savings-cron"}


@pytest.mark.parametrize("roles", [(), ("internal",), ("simulator",)])
async def test_require_sim_refuses_without_the_sim_role(routes, as_user, roles):
    r = await as_user("anyone", roles=roles).post("/_test/sim")
    assert r.status_code == 403 and await code(r) == "forbidden"


async def test_require_sim_accepts_the_sim_role(routes, as_user):
    r = await as_user("operator", roles=("sim",)).post("/_test/sim")
    assert r.status_code == 200 and r.json() == {"sub": "operator"}
