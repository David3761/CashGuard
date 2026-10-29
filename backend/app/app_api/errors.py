"""`{"message": "..."}` errors on the app API's routes only (API_SPEC.md "Errors").

The `/api` routes keep the arch 9.1 envelope `{"error": {"code", "message"}}`. This route class
wraps FastAPI's handler, so a `DomainError`, an `HTTPException`, a body that fails validation
(both raised inside the handler, dependencies included) or a crash become a bare message.
A router-level 404/405 (no route matched) still gets the global envelope; the app shows a
generic error for any failure of those calls.
"""

import logging
from collections.abc import Callable, Coroutine, Mapping
from typing import Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.errors import DomainError

log = logging.getLogger(__name__)

INTERNAL_ERROR = "Something went wrong. Please try again."
MAX_BODY_BYTES = 16 * 1024  # checked on Content-Length before the body is read
TOO_LARGE = "The request is too large."


class AppError(BaseModel):
    """Every non-2xx body of an app route."""

    message: str


def message_response(
    status: int, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"message": message}, headers=dict(headers or {})
    )


def _validation_message(exc: RequestValidationError) -> str:
    errors: list[Any] = list(exc.errors())
    first = errors[0] if errors else {}
    location = [str(part) for part in first.get("loc", ()) if part != "body"]
    if not location:
        return "The request body must be a JSON object."
    return f"Invalid request: {'.'.join(location)} is missing or has the wrong type."


class MessageErrorRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_BODY_BYTES:
                return message_response(413, TOO_LARGE)
            try:
                return await handler(request)
            except RequestValidationError as exc:
                return message_response(422, _validation_message(exc))
            except DomainError as exc:
                return message_response(exc.status, exc.message, exc.headers)
            except StarletteHTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, str) else INTERNAL_ERROR
                return message_response(exc.status_code, detail, exc.headers)
            except Exception:
                log.exception("app api: unhandled error on %s %s", request.method, request.url.path)
                return message_response(500, INTERNAL_ERROR)

        return handle
