"""HTTP hardening for every response (security review P1-6, P1-11): security headers and a
request body size limit, as one pure-ASGI middleware.

Pure ASGI (no BaseHTTPMiddleware), so nothing is buffered: a streamed response (SSE) passes
through chunk by chunk with only its start message touched, and WebSocket / lifespan scopes are
not touched at all.

Headers (a header the route already set wins):
- `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`;
- `Content-Security-Policy`: `default-src 'none'` for the JSON API (nothing to load, nothing
  to frame); the Swagger page (/api/docs, only when API_DOCS_ENABLED) gets the looser policy it
  needs for its CDN script and styles;
- `Cache-Control: no-store` on /api/* (financial data must not sit in caches);
- `Strict-Transport-Security` when the app runs outside the simulator/dev mode, and on any
  request that came over HTTPS (Caddy terminates TLS; uvicorn's --proxy-headers sets the scheme).

Body limit: a `Content-Length` over `max_body_bytes` gets 413 `payload_too_large` before the
app reads anything; a chunked body is counted while the app reads it, and stops at the limit.
"""

from typing import Final

from fastapi import HTTPException
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import error_response

MAX_BODY_BYTES: Final = 64 * 1024
HSTS: Final = "max-age=31536000; includeSubDomains"
API_CSP: Final = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
DOCS_CSP: Final = (
    "default-src 'none'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
DOCS_PATHS: Final = frozenset({"/api/docs", "/api/docs/oauth2-redirect"})
TOO_LARGE_MESSAGE: Final = "The request body is too large."


class HardeningMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool, max_body_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.hsts = hsts
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        extra = self._headers(path, https=scope.get("scheme") == "https")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(raw=list(message.get("headers", [])))
                for name, value in extra.items():
                    if name not in headers:
                        headers[name] = value
                message["headers"] = headers.raw
            await send(message)

        length = Headers(scope=scope).get("content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_body_bytes):
            response = error_response(413, "payload_too_large", TOO_LARGE_MESSAGE)
            await response(scope, receive, send_with_headers)
            return
        await self.app(scope, self._limited(receive), send_with_headers)

    def _headers(self, path: str, *, https: bool) -> dict[str, str]:
        headers = {
            "x-content-type-options": "nosniff",
            "x-frame-options": "DENY",
            "referrer-policy": "no-referrer",
            "content-security-policy": DOCS_CSP if path in DOCS_PATHS else API_CSP,
        }
        if path.startswith("/api/"):
            headers["cache-control"] = "no-store"
        if self.hsts or https:
            headers["strict-transport-security"] = HSTS
        return headers

    def _limited(self, receive: Receive) -> Receive:
        """`receive`, refusing the body once more than `max_body_bytes` arrived (chunked
        uploads have no Content-Length to check up front)."""
        seen = 0

        async def limited() -> Message:
            nonlocal seen
            message = await receive()
            if message["type"] == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_body_bytes:
                    # FastAPI re-raises an HTTPException met while reading the body; the app's
                    # handler answers it with the envelope (413 payload_too_large).
                    raise HTTPException(status_code=413, detail=TOO_LARGE_MESSAGE)
            return message

        return limited
