"""Keycloak JWT verification (arch 5.1, B5).

Error codes (arch 9.1 envelope): missing_token, invalid_token, token_expired, invalid_issuer,
invalid_audience, unknown_user (401); forbidden (403); auth_unavailable (503).
Only access tokens are accepted (`typ: Bearer`): a Keycloak ID or refresh token is refused.
Token times are checked against the real clock: tokens come from Keycloak, not the simulator.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any

import httpx
import jwt
from fastapi import Depends, Header
from jwt import PyJWK
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.session import get_db
from app.domain.models import UserProfile
from app.errors import DomainError
from app.services import users

log = logging.getLogger(__name__)

ACCEPTED_CLIENTS = frozenset({"savings-frontend", "savings-dev", "savings-cron"})
# Keycloak's `typ` claim: "Bearer" (access), "ID", "Refresh". A token type, not a password.
ACCESS_TOKEN_TYPE = "Bearer"  # noqa: S105  # nosec B105
SIM_ROLE = "sim"  # realm role of the demo operator: may drive /api/sim/*
LEEWAY_SECONDS = 30
REFETCH_INTERVAL_SECONDS = 60.0


def _unauthorized(code: str, message: str) -> DomainError:
    return DomainError(code, message, status=401)


@dataclass(frozen=True)
class Claims:
    sub: str
    azp: str | None
    roles: frozenset[str]
    raw: dict[str, Any]


class JWKSCache:
    """Signing keys by `kid`, from `<base_url>/.well-known/openid-configuration` → `jwks_uri`.
    An unknown `kid` refetches at most once per 60 s (key rotation without a DoS lever)."""

    def __init__(
        self,
        base_url: str,
        *,
        now: Callable[[], float] = time.monotonic,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._now = now
        self._timeout = timeout
        self._keys: dict[str, PyJWK] = {}
        self._loaded = False
        self._unknown_kid_refetch_at: float | None = None
        self._lock = asyncio.Lock()

    def preload(self, jwks: dict[str, Any]) -> None:
        """Use these keys as if just fetched (tests, warm start)."""
        self._keys = self._signing_keys(jwks)
        self._loaded = True

    async def get_key(self, kid: str) -> PyJWK:
        if kid in self._keys:
            return self._keys[kid]
        async with self._lock:
            if not self._loaded:
                await self._refresh()
            elif kid not in self._keys and self._may_refetch_for_unknown_kid():
                self._unknown_kid_refetch_at = self._now()
                await self._refresh()
        if kid not in self._keys:
            raise _unauthorized("invalid_token", "The token is signed with an unknown key.")
        return self._keys[kid]

    def _may_refetch_for_unknown_kid(self) -> bool:
        last = self._unknown_kid_refetch_at
        return last is None or self._now() - last >= REFETCH_INTERVAL_SECONDS

    async def _refresh(self) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http:
                discovery = await http.get(f"{self.base_url}/.well-known/openid-configuration")
                discovery.raise_for_status()
                certs = await http.get(discovery.json()["jwks_uri"])
                certs.raise_for_status()
                keys = self._signing_keys(certs.json())
        except (httpx.HTTPError, KeyError, ValueError, jwt.PyJWTError) as exc:
            log.warning("JWKS fetch from %s failed: %s", self.base_url, exc)
            raise DomainError(
                "auth_unavailable", "The login service can't be reached. Try again.", status=503
            ) from exc
        self._keys = keys
        self._loaded = True

    @staticmethod
    def _signing_keys(jwks: dict[str, Any]) -> dict[str, PyJWK]:
        return {
            k["kid"]: PyJWK(k)
            for k in jwks.get("keys", [])
            if k.get("use", "sig") == "sig" and k.get("alg", "RS256") == "RS256" and "kid" in k
        }


_jwks: JWKSCache | None = None


def get_jwks() -> JWKSCache:
    global _jwks
    if _jwks is None:
        settings = get_settings()
        url = settings.KEYCLOAK_INTERNAL_URL or settings.KEYCLOAK_ISSUER
        if url is None:
            raise DomainError("auth_unavailable", "Keycloak is not configured.", status=503)
        _jwks = JWKSCache(url)
    return _jwks


def set_jwks(cache: JWKSCache | None) -> None:
    """Replace the key source (tests); None = rebuild from settings on next use."""
    global _jwks
    _jwks = cache


async def verify_token(token: str) -> Claims:
    """Check signature (RS256 only), `iss`, `exp`/`nbf` (30 s leeway), `typ` (access tokens
    only) and `azp`/`aud`."""
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise _unauthorized("invalid_token", "The token is malformed.") from exc
    kid = header.get("kid")
    if header.get("alg") != "RS256" or not isinstance(kid, str):
        raise _unauthorized("invalid_token", "The token's algorithm or key id is not accepted.")

    key = await get_jwks().get_key(kid)
    settings = get_settings()
    try:
        raw: dict[str, Any] = jwt.decode(
            token,
            key=key.key,
            algorithms=["RS256"],
            issuer=settings.KEYCLOAK_ISSUER,
            leeway=LEEWAY_SECONDS,
            # The audience IS checked, by hand below: Keycloak names our client in `azp` and
            # often leaves `aud` out (or sets it to "account"), so "azp in ACCEPTED_CLIENTS OR
            # KEYCLOAK_AUDIENCE in aud" can't be expressed with PyJWT's `audience=`.
            options={"verify_aud": False, "require": ["exp", "iat", "iss", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise _unauthorized("token_expired", "The token expired. Refresh it and retry.") from exc
    except jwt.InvalidIssuerError as exc:
        raise _unauthorized("invalid_issuer", "The token was issued by another server.") from exc
    except jwt.PyJWTError as exc:
        raise _unauthorized("invalid_token", "The token is not valid.") from exc

    if raw.get("typ") != ACCESS_TOKEN_TYPE:
        raise _unauthorized("invalid_token", "Send an access token, not an ID or refresh token.")

    azp = raw.get("azp")
    aud = raw.get("aud")
    audiences = {aud} if isinstance(aud, str) else set(aud or [])
    if azp not in ACCEPTED_CLIENTS and settings.KEYCLOAK_AUDIENCE not in audiences:
        raise _unauthorized("invalid_audience", "The token is not meant for this API.")

    roles = raw.get("realm_access", {}).get("roles", [])
    return Claims(sub=str(raw["sub"]), azp=azp, roles=frozenset(roles), raw=raw)


# ── FastAPI dependencies (B5 step 2) ─────────────────────────────────────────────────────


def bearer_token(authorization: str | None) -> str:
    """The token of an `Authorization: Bearer <token>` header (scheme case-insensitive)."""
    scheme, _, token = (authorization or "").strip().partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("missing_token", "Send `Authorization: Bearer <access token>`.")
    return token.strip()


async def current_claims(
    authorization: Annotated[str | None, Header()] = None,
) -> Claims:
    return await verify_token(bearer_token(authorization))


async def require_internal(claims: Annotated[Claims, Depends(current_claims)]) -> Claims:
    """`/internal/*`: only tokens with the realm role `internal` (the cron client)."""
    if "internal" not in claims.roles:
        raise DomainError("forbidden", "This endpoint is for internal jobs only.", status=403)
    return claims


async def require_sim(claims: Annotated[Claims, Depends(current_claims)]) -> Claims:
    """`/sim/*`: only the demo operator (realm role `sim`). The simulator writes into any
    persona, moves the global clock and reseeds every user, so a plain login is not enough."""
    if SIM_ROLE not in claims.roles:
        raise DomainError("forbidden", "The simulator is for the demo operator only.", status=403)
    return claims


async def user_for_claims(db: AsyncSession, claims: Claims) -> UserProfile:
    user = await users.get_by_sub(db, claims.sub)
    if user is None:
        raise _unauthorized("unknown_user", "No CashGuard user for this login.")
    return user


async def current_user(
    claims: Annotated[Claims, Depends(current_claims)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserProfile:
    """The user of the request: Bearer token → claims → `users.keycloak_sub`. The only user id
    used anywhere (arch 5.1)."""
    return await user_for_claims(db, claims)


async def ws_auth(db: AsyncSession, token: str | None) -> tuple[UserProfile, Claims]:
    """WebSocket auth (`/ws?token=`): the user and the token's claims (the socket re-checks
    `exp` while it is open). Raises DomainError; the route closes with 1008."""
    if not token:
        raise _unauthorized("missing_token", "Pass the access token as ?token=.")
    claims = await verify_token(token)
    return await user_for_claims(db, claims), claims


async def ws_user(db: AsyncSession, token: str | None) -> UserProfile:
    """WebSocket auth, the user only (see `ws_auth`)."""
    user, _ = await ws_auth(db, token)
    return user
