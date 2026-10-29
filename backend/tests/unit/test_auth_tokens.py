"""B5 step 1: token verification and the JWKS cache (no network: respx mocks Keycloak)."""

import httpx
import pytest
import respx

from app import auth
from app.config import get_settings
from app.errors import DomainError
from tests.fixtures.auth import (
    MATEI_SUB,
    claims,
    hs256_with_public_key,
    new_keys,
    sign,
    unsigned_token,
)

BASE = "http://kc.test/realms/cashguard"
DISCOVERY = f"{BASE}/.well-known/openid-configuration"
JWKS_URI = f"{BASE}/protocol/openid-connect/certs"


async def rejected(token: str, code: str, status: int = 401) -> None:
    with pytest.raises(DomainError) as err:
        await auth.verify_token(token)
    assert (err.value.code, err.value.status) == (code, status)


# ── verify_token (JWKS = the test key) ───────────────────────────────────────────────────


async def test_valid_token_gives_its_claims(make_token, test_jwks):
    c = await auth.verify_token(make_token(roles=("internal",)))
    assert c.sub == MATEI_SUB
    assert c.azp == "savings-frontend"
    assert "internal" in c.roles


@pytest.mark.parametrize("azp", ["savings-frontend", "savings-dev", "savings-cron"])
async def test_each_of_our_clients_is_accepted(make_token, test_jwks, azp):
    assert (await auth.verify_token(make_token(azp=azp))).azp == azp


async def test_audience_instead_of_azp_is_accepted(make_token, test_jwks):
    token = make_token(azp="other-client", aud=["account", get_settings().KEYCLOAK_AUDIENCE])
    assert (await auth.verify_token(token)).sub == MATEI_SUB


async def test_expired_token(make_token, test_jwks):
    await rejected(make_token(exp_in=-31), "token_expired")


async def test_expiry_leeway_is_30_seconds(make_token, test_jwks):
    await auth.verify_token(make_token(exp_in=-25))


async def test_not_yet_valid_token(make_token, test_jwks):
    await rejected(make_token(nbf_in=120), "invalid_token")


async def test_wrong_issuer(make_token, test_jwks):
    # the classic emulator mismatch (D36): same realm, another host
    await rejected(make_token(iss="http://10.0.2.2:8080/realms/cashguard"), "invalid_issuer")


@pytest.mark.parametrize(
    "kw", [{"azp": "evil-client"}, {"azp": None, "aud": "account"}, {"azp": None}]
)
async def test_wrong_client_or_audience(make_token, test_jwks, kw):
    await rejected(make_token(**kw), "invalid_audience")


async def test_missing_sub(test_keys, test_jwks):
    body = claims()
    del body["sub"]
    await rejected(sign(test_keys, body), "invalid_token")


async def test_alg_none_rejected(test_jwks):
    await rejected(unsigned_token(claims()), "invalid_token")


async def test_hs256_signed_with_the_public_key_rejected(test_keys, test_jwks):
    await rejected(hs256_with_public_key(test_keys, claims()), "invalid_token")


async def test_signed_by_another_key_with_our_kid_rejected(test_jwks):
    await rejected(sign(new_keys(), claims()), "invalid_token")


@pytest.mark.parametrize("typ", ["ID", "Refresh", "Logout", "bearer", ""])
async def test_only_access_tokens_are_accepted(make_token, test_jwks, typ):
    # A Keycloak ID token has the same iss/sub/azp and signature as an access token: refuse it.
    await rejected(make_token(typ=typ), "invalid_token")


async def test_token_without_typ_is_rejected(test_keys, test_jwks):
    body = claims()
    del body["typ"]
    await rejected(sign(test_keys, body), "invalid_token")


@pytest.mark.parametrize("token", ["", "garbage", "a.b.c", "Bearer x.y.z"])
async def test_malformed_token(test_jwks, token):
    await rejected(token, "invalid_token")


# ── the JWKS cache against a mocked Keycloak ─────────────────────────────────────────────


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


@pytest.fixture
def keycloak(test_keys):
    with respx.mock(assert_all_called=False) as mock:
        discovery = mock.get(DISCOVERY).respond(json={"issuer": BASE, "jwks_uri": JWKS_URI})
        certs = mock.get(JWKS_URI).respond(
            json={
                "keys": [
                    test_keys.public_jwk,
                    {
                        "kid": "enc",
                        "kty": "RSA",
                        "use": "enc",
                        "alg": "RSA-OAEP",
                        "n": test_keys.public_jwk["n"],
                        "e": "AQAB",
                    },
                ]
            }
        )
        yield discovery, certs


@pytest.fixture
def cache():
    tick = Clock()
    c = auth.JWKSCache(BASE, now=tick)
    auth.set_jwks(c)
    yield c, tick
    auth.set_jwks(None)


async def test_cache_fetches_discovery_then_keys_once(keycloak, cache, make_token):
    discovery, certs = keycloak
    await auth.verify_token(make_token())
    await auth.verify_token(make_token())
    assert (discovery.call_count, certs.call_count) == (1, 1)


async def test_unknown_kid_refetches_at_most_once_per_60_seconds(keycloak, cache, make_token):
    _, certs = keycloak
    _, tick = cache
    await auth.verify_token(make_token())  # warm: 1 fetch
    await rejected(make_token(kid="rotated"), "invalid_token")  # refetch: 2
    await rejected(make_token(kid="rotated"), "invalid_token")  # within 60 s: no fetch
    assert certs.call_count == 2
    tick.t += 61
    await rejected(make_token(kid="rotated"), "invalid_token")
    assert certs.call_count == 3


async def test_encryption_keys_are_ignored(keycloak, cache, make_token):
    await rejected(make_token(kid="enc"), "invalid_token")


async def test_keycloak_down_with_an_empty_cache_is_503(cache, make_token):
    with respx.mock() as mock:
        mock.get(DISCOVERY).mock(side_effect=httpx.ConnectError("down"))
        await rejected(make_token(), "auth_unavailable", 503)


async def test_keycloak_down_with_a_warm_cache_still_validates(keycloak, cache, make_token):
    await auth.verify_token(make_token())  # warm
    with respx.mock(assert_all_called=False) as mock:
        route = mock.get(DISCOVERY).mock(side_effect=httpx.ConnectError("down"))
        assert (await auth.verify_token(make_token())).sub == MATEI_SUB
        assert route.call_count == 0


async def test_keycloak_returning_garbage_is_503(cache, make_token):
    with respx.mock() as mock:
        mock.get(DISCOVERY).respond(500)
        await rejected(make_token(), "auth_unavailable", 503)


def test_default_cache_uses_the_internal_url_when_set(monkeypatch):
    monkeypatch.setenv("KEYCLOAK_INTERNAL_URL", "http://keycloak:8080/realms/cashguard")
    get_settings.cache_clear()
    try:
        auth.set_jwks(None)
        assert auth.get_jwks().base_url == "http://keycloak:8080/realms/cashguard"
    finally:
        get_settings.cache_clear()
        auth.set_jwks(None)
