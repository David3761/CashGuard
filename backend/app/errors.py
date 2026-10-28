"""`DomainError` and the handlers that turn every failure into the arch 9.1 envelope:

{"error": {"code": "agent_busy", "message": "..."}}
"""

import logging
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
}


class DomainError(Exception):
    """A failure with a stable machine-readable `code` (listed per task in the work breakdown)."""

    def __init__(self, code: str, message: str | None = None, status: int = 400) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.status = status


def error_response(
    status: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {"error": {"code": code, "message": message}}
    return JSONResponse(status_code=status, content=body, headers=headers)


async def _domain_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return error_response(exc.status, exc.code, exc.message)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", ()))
    message = f"{where}: {first.get('msg', 'invalid value')}" if where else "Invalid request."
    return error_response(422, "invalid_request", message)


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else code
    return error_response(exc.status_code, code, message, headers=exc.headers)


async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled error", exc_info=exc)
    return error_response(500, "internal_error", "Something went wrong. Please try again.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
