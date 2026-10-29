"""Auth fixtures (F3 step 2): one RSA key per test session, tokens shaped like Keycloak's, and
the app's JWKS cache pointed at the test key.

    def test_x(make_token, test_jwks):
        token = make_token(sub="a0000000-…-01", roles=("internal",), exp_in=-1)
"""

import base64
import hashlib
import hmac
import json
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from app import auth, clock
from app.config import get_settings

TEST_KID = "test"
LOCAL_ISSUER = "http://localhost:8081/realms/cashguard"  # bomboe's local Keycloak (B1/B5)
MATEI_SUB = "a0000000-0000-4000-8000-000000000001"


@dataclass(frozen=True)
class TestKeys:
    private_key: rsa.RSAPrivateKey
    kid: str

    @property
    def public_jwk(self) -> dict[str, Any]:
        jwk = RSAAlgorithm.to_jwk(self.private_key.public_key(), as_dict=True)
        return {**jwk, "kid": self.kid, "use": "sig", "alg": "RS256"}

    @property
    def public_pem(self) -> bytes:
        return self.private_key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )

    def jwks(self) -> dict[str, Any]:
        return {"keys": [self.public_jwk]}


def new_keys(kid: str = TEST_KID) -> TestKeys:
    return TestKeys(rsa.generate_private_key(public_exponent=65537, key_size=2048), kid)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def claims(
    sub: str = MATEI_SUB,
    roles: tuple[str, ...] = (),
    exp_in: int = 300,
    iss: str | None = None,
    azp: str | None = "savings-frontend",
    aud: str | list[str] | None = None,
    nbf_in: int | None = None,
    **extra: Any,
) -> dict[str, Any]:
    # real time: tokens come from Keycloak's clock, not the simulator's (RealClock, never time.time)
    now = int(clock.RealClock().now().timestamp())
    body: dict[str, Any] = {
        # unit tests run without KEYCLOAK_ISSUER (the code default is unset): sign for local
        "iss": iss or get_settings().KEYCLOAK_ISSUER or LOCAL_ISSUER,
        "sub": sub,
        "iat": now,
        "exp": now + exp_in,
        "jti": str(uuid.uuid4()),
        "typ": "Bearer",
        "realm_access": {"roles": ["default-roles-cashguard", *roles]},
    }
    if azp is not None:
        body["azp"] = azp
    if aud is not None:
        body["aud"] = aud
    if nbf_in is not None:
        body["nbf"] = now + nbf_in
    return body | extra


def sign(keys: TestKeys, body: dict[str, Any], *, kid: str | None = None) -> str:
    return jwt.encode(body, keys.private_key, algorithm="RS256", headers={"kid": kid or keys.kid})


def unsigned_token(body: dict[str, Any], kid: str = TEST_KID) -> str:
    """`alg: none` (no signature): must be rejected."""
    header = {"alg": "none", "typ": "JWT", "kid": kid}
    return f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(body).encode())}."


def hs256_with_public_key(keys: TestKeys, body: dict[str, Any]) -> str:
    """Algorithm confusion: HMAC-signed with the *public* key as the secret. Must be rejected."""
    header = {"alg": "HS256", "typ": "JWT", "kid": keys.kid}
    signing_input = f"{_b64(json.dumps(header).encode())}.{_b64(json.dumps(body).encode())}"
    sig = hmac.new(keys.public_pem, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(sig)}"


@pytest.fixture(scope="session")
def test_keys() -> TestKeys:
    return new_keys()


@pytest.fixture
def make_token(test_keys: TestKeys) -> Callable[..., str]:
    """`make_token(sub=…, roles=(), exp_in=300, iss=…, azp="savings-frontend", aud=None,
    nbf_in=None, kid="test")` → a signed access token."""

    def _make(kid: str | None = None, **kw: Any) -> str:
        return sign(test_keys, claims(**kw), kid=kid)

    return _make


@pytest.fixture
def test_jwks(test_keys: TestKeys) -> Iterator[auth.JWKSCache]:
    """The app verifies tokens against the test key (no Keycloak, no network)."""
    cache = auth.JWKSCache("http://keycloak.invalid/realms/cashguard")
    cache.preload(test_keys.jwks())
    auth.set_jwks(cache)
    yield cache
    auth.set_jwks(None)
