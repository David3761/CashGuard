"""Firebase Cloud Messaging, HTTP v1 (API_SPEC.md "Push payload").

- Auth: the Firebase project's service-account key (`FCM_SERVICE_ACCOUNT_FILE`, server only).
  An RS256 JWT signed with it is exchanged for an OAuth access token (1 h), cached until a
  minute before it expires. The JWT's `iat` is **real** time (Google rejects simulator time).
- Messages are **data-only** (no `notification` block, or Android shows a second notification)
  and every data value is a string (FCM requires it). The app reads `data.message`.
- A token FCM says is gone (404 UNREGISTERED, 403 SENDER_ID_MISMATCH) is reported `dead`, so the
  caller deletes it. 401 → one token refresh and one retry. Anything else is logged, never raised.
- Logs never carry a whole device token or any secret.
"""

import asyncio
import json
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol

import httpx
import jwt

from app import clock
from app.config import Settings

log = logging.getLogger(__name__)

SCOPE: Final = "https://www.googleapis.com/auth/firebase.messaging"
SEND_URL: Final = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"
TOKEN_LIFETIME_S: Final = 3600
REFRESH_MARGIN_S: Final = 60
TIMEOUT_S: Final = 5.0
DEAD_CODES: Final = frozenset({"UNREGISTERED", "SENDER_ID_MISMATCH"})

PushResult = Literal["sent", "dead", "failed", "skipped"]


class PushSender(Protocol):
    async def send(self, token: str, data: Mapping[str, str]) -> PushResult: ...


def short(token: str) -> str:
    """A device token as it may appear in a log line."""
    return f"{token[:8]}…" if len(token) > 8 else "…"


def wall_seconds() -> float:
    """Real Unix time (through app.clock, the only module allowed to read the wall clock)."""
    return clock.RealClock().now().timestamp()


@dataclass(frozen=True, slots=True)
class ServiceAccount:
    client_email: str
    private_key: str
    token_uri: str
    project_id: str

    def __repr__(self) -> str:  # never print the key
        return f"ServiceAccount({self.client_email!r}, project={self.project_id!r})"


def load_service_account(path: Path) -> ServiceAccount:
    """Read the key file; a missing file or field is a ValueError naming it (not the key)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as err:
        raise ValueError(
            f"FCM_SERVICE_ACCOUNT_FILE: can't read {path.name} ({type(err).__name__})"
        ) from None
    if not isinstance(raw, dict):
        raise ValueError("FCM_SERVICE_ACCOUNT_FILE: not a service-account JSON object")
    fields = ("client_email", "private_key", "token_uri", "project_id")
    missing = [name for name in fields if not isinstance(raw.get(name), str) or not raw[name]]
    if missing:
        raise ValueError(f"FCM_SERVICE_ACCOUNT_FILE: missing {', '.join(missing)}")
    return ServiceAccount(*(raw[name] for name in fields))


def message_body(token: str, data: Mapping[str, str]) -> dict[str, Any]:
    """The HTTP v1 request body: data-only, string values, high priority on Android."""
    return {
        "message": {
            "token": token,
            "data": {str(key): str(value) for key, value in data.items()},
            "android": {"priority": "high"},
        }
    }


def _error_code(response: httpx.Response) -> str | None:
    try:
        error = response.json().get("error", {})
    except ValueError:
        return None
    for detail in error.get("details", []) or []:
        if isinstance(detail, dict) and detail.get("errorCode"):
            return str(detail["errorCode"])
    status = error.get("status")
    return str(status) if status else None


class FcmSender:
    def __init__(
        self,
        account: ServiceAccount,
        *,
        project_id: str | None = None,
        client: httpx.AsyncClient | None = None,
        now: Callable[[], float] = wall_seconds,
    ) -> None:
        self._account = account
        self._project = project_id or account.project_id
        self._client = client or httpx.AsyncClient(timeout=TIMEOUT_S)
        self._now = now
        self._token: str | None = None
        self._expires = 0.0
        self._lock = asyncio.Lock()

    def assertion(self) -> str:
        issued = int(self._now())
        claims = {
            "iss": self._account.client_email,
            "scope": SCOPE,
            "aud": self._account.token_uri,
            "iat": issued,
            "exp": issued + TOKEN_LIFETIME_S,
        }
        return jwt.encode(claims, self._account.private_key, algorithm="RS256")

    async def access_token(self, *, refresh: bool = False) -> str:
        async with self._lock:
            if not refresh and self._token and self._now() < self._expires - REFRESH_MARGIN_S:
                return self._token
            response = await self._client.post(
                self._account.token_uri,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": self.assertion(),
                },
            )
            response.raise_for_status()
            body = response.json()
            self._token = str(body["access_token"])
            self._expires = self._now() + float(body.get("expires_in", TOKEN_LIFETIME_S))
            return self._token

    async def send(self, token: str, data: Mapping[str, str]) -> PushResult:
        url = SEND_URL.format(project=self._project)
        try:
            for attempt in range(2):
                bearer = await self.access_token(refresh=attempt > 0)
                response = await self._client.post(
                    url,
                    json=message_body(token, data),
                    headers={"Authorization": f"Bearer {bearer}"},
                )
                if response.status_code == 401 and attempt == 0:
                    continue
                break
        except (httpx.HTTPError, KeyError, ValueError) as err:
            log.warning("fcm: push to %s failed (%s)", short(token), type(err).__name__)
            return "failed"
        if response.is_success:
            return "sent"
        code = _error_code(response)
        if response.status_code in {403, 404} and code in DEAD_CODES:
            log.info("fcm: token %s is gone (%s)", short(token), code)
            return "dead"
        log.warning("fcm: push to %s failed: HTTP %s %s", short(token), response.status_code, code)
        return "failed"


class NullSender:
    """No key configured: pushes are logged and skipped."""

    async def send(self, token: str, data: Mapping[str, str]) -> PushResult:
        log.info("fcm disabled (no FCM_SERVICE_ACCOUNT_FILE): skipped a push to %s", short(token))
        return "skipped"


def sender_from_settings(settings: Settings) -> PushSender | None:
    """The FCM sender, or None when no key file is configured."""
    if settings.FCM_SERVICE_ACCOUNT_FILE is None:
        return None
    account = load_service_account(settings.FCM_SERVICE_ACCOUNT_FILE)
    return FcmSender(account, project_id=settings.FCM_PROJECT_ID)
