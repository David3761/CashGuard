"""The app API's optional shared key (`APP_API_KEY`): when it is set, every app route needs the
header `X-App-Key`.

The app has one demo user and no login, so this isn't per-user auth: it keeps the financial data
and the paid Claude calls of a public host away from anyone who only knows the URL. The key ships
inside the app build (`--dart-define=APP_API_KEY=…`), so it is a shared secret to rotate, not a
user credential. Unset (the local demo) → the routes stay open, as before.

`require_app_key` is a router dependency, so FastAPI runs it before each route's own dependencies:
a call without the key never reaches the `chat` rate limit (it can't use up the one shared "app"
bucket), the database or the agent. A missing and a wrong key get the same 401 `{"message"}`, the
comparison is constant-time, and the key is never logged or echoed.
"""

import hmac
from typing import Annotated, Final

from fastapi import Depends
from fastapi.security import APIKeyHeader

from app.config import Settings, get_app_settings
from app.errors import DomainError

APP_KEY_HEADER: Final = "X-App-Key"
UNAUTHORIZED: Final = "This app isn't allowed to use the server: its app key is missing or wrong."

_scheme = APIKeyHeader(
    name=APP_KEY_HEADER,
    auto_error=False,  # a missing key is our 401 `{"message"}`, and only when a key is set
    scheme_name="AppKey",
    description="The server's APP_API_KEY. Required only when the server sets one.",
)


def key_matches(given: str | None, expected: str) -> bool:
    """Constant-time. Bytes, because `compare_digest` refuses non-ASCII text (that would be a
    500); a non-ASCII key just never matches."""
    if not given:
        return False
    return hmac.compare_digest(given.encode(), expected.encode())


async def require_app_key(
    settings: Annotated[Settings, Depends(get_app_settings)],
    given: Annotated[str | None, Depends(_scheme)],
) -> None:
    """FastAPI dependency: nothing to do without `APP_API_KEY`, else the header must match."""
    if settings.APP_API_KEY is None:
        return
    if not key_matches(given, settings.APP_API_KEY.get_secret_value()):
        raise DomainError("app_key_invalid", UNAUTHORIZED, status=401)
