"""B8 step 4: /internal/process and /internal/recover need the `internal` role."""

import pytest


@pytest.mark.parametrize("path", ["/internal/process", "/internal/recover"])
async def test_internal_endpoints_need_the_role(as_user, path):
    r = await as_user("someone").post(path)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("path", ["/internal/process", "/internal/recover"])
async def test_internal_endpoints_without_a_token(client, path):
    assert (await client.post(path)).status_code == 401
