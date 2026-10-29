"""The error envelope (F1.4): every non-2xx response is `{"error": {"code", "message"}}` (arch 9.1).

Raise `DomainError(code, message, status)` with a stable snake_case `code` (work-breakdown 0.3
rule 5), anywhere: in a route, a dependency or a middleware. On a WebSocket it closes the socket
instead (1008, or 1011 for 5xx; the reason is the code). Messages are English developer/Claude
text: the app maps `code` to its own UI text, so `app/i18n` isn't involved.

F1's own codes: `validation_error` (422), `not_found` (404), `method_not_allowed` (405),
`internal_error` (500), and `http_<status>` for any other framework HTTP error. Nothing a client
sent (values, dict keys, unknown field names) and no internal name ever comes back in a message.
"""

import re
from collections.abc import Mapping, Sequence
from http import HTTPStatus
from types import MappingProxyType, UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.routing import iter_route_contexts
from fastapi.utils import is_body_allowed_for_status_code
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware import Middleware
from starlette.requests import HTTPConnection, Request
from starlette.routing import BaseRoute, Match, Mount
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocket

_CODE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
_MAX_CODE_LENGTH = 64
_FORBIDDEN_HEADERS = frozenset({"content-length", "content-type"})  # the response sets these
_INTERNAL_ERROR_MESSAGE = "Something went wrong on our side. Please try again."
_CODES_BY_STATUS = {404: "not_found", 405: "method_not_allowed", 413: "payload_too_large"}
_STANDARD_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})


class DomainError(Exception):
    """An expected failure with a stable `code` the client can branch on, e.g. `agent_busy`.

    `headers` go on the response, e.g. `WWW-Authenticate` on a 401 (RFC 9110), `Retry-After`."""

    def __init__(
        self,
        code: str,
        message: str,
        status: int = 400,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        if not isinstance(code, str) or len(code) > _MAX_CODE_LENGTH or not _CODE.fullmatch(code):
            raise ValueError(f"DomainError code must be snake_case (≤ 64 chars), got {code!r}")
        if not isinstance(status, int) or not 400 <= status <= 599:  # (a bool is 0 or 1)
            raise ValueError(f"DomainError status must be an int in 400-599, got {status!r}")
        if not isinstance(message, str) or not message.strip():
            raise ValueError("DomainError needs a message (clear enough to act on)")
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.headers: Mapping[str, str] = _checked_headers(headers)


def _checked_headers(headers: Mapping[str, str] | None) -> Mapping[str, str]:
    checked: dict[str, str] = {}
    for name, value in (headers or {}).items():
        text = f"{name}{value}" if isinstance(name, str) and isinstance(value, str) else None
        if text is None or not name.strip() or any(char in text for char in "\r\n\0"):
            raise ValueError(f"DomainError header {name!r} must be a single-line string")
        if name.lower() in _FORBIDDEN_HEADERS:
            raise ValueError(f"DomainError headers can't set {name} (the response does)")
        checked[name] = value
    return MappingProxyType(checked)


class ErrorBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str


class ErrorEnvelope(BaseModel):
    """`{"error": {"code": "agent_busy", "message": "…"}}` (arch 9.1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    error: ErrorBody


# For `FastAPI(responses=…)`: every route documents the envelope. A "default" entry also stops
# FastAPI from advertising its own 422 shape (`HTTPValidationError`), which we never send.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    "default": {"model": ErrorEnvelope, "description": "Error (arch 9.1 envelope)"},
}


def error_response(
    status: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> Response:
    """The arch 9.1 envelope as a response (bomboe's helper, e.g. for the WS/auth paths)."""
    return _envelope(status, code, message, headers)


# ── sending an error ─────────────────────────────────────────────────────────────────────────


def _envelope(
    status: int, code: str, message: str, headers: Mapping[str, str] | None = None
) -> Response:
    if not is_body_allowed_for_status_code(status):
        return Response(status_code=status, headers=headers)
    body = ErrorEnvelope(error=ErrorBody(code=code, message=message))
    return JSONResponse(body.model_dump(), status_code=status, headers=headers)


def _close_code(status: int) -> int:
    return 1011 if status >= 500 else 1008  # internal error / policy violation (arch 5.1)


async def _reply(
    conn: HTTPConnection,
    status: int,
    code: str,
    message: str,
    headers: Mapping[str, str] | None = None,
) -> Response | None:
    """The envelope for HTTP; on a WebSocket, close it (the reason is the code, never details)."""
    if isinstance(conn, WebSocket):
        await conn.close(code=_close_code(status), reason=code)
        return None
    return _envelope(status, code, message, headers)


def _phrase(status: int) -> str:
    try:
        return HTTPStatus(status).phrase
    except ValueError:  # a status Python doesn't know, e.g. 499
        return "Error"


# ── validation messages: the field path and a fixed text, never what was sent ───────────────

_TEXTS: dict[str, str] = {
    "missing": "field required",
    "extra_forbidden": "unknown field",
    "json_invalid": "invalid JSON",
    "json_type": "must be valid JSON",
    "int_type": "must be an integer",
    "int_parsing": "must be an integer",
    "int_from_float": "must be an integer",
    "float_type": "must be a number",
    "float_parsing": "must be a number",
    "finite_number": "must be a finite number",
    "decimal_type": "must be a decimal number",
    "decimal_parsing": "must be a decimal number",
    "decimal_max_digits": "has too many digits",
    "decimal_max_places": "has too many decimal places",
    "bool_type": "must be true or false",
    "bool_parsing": "must be true or false",
    "string_type": "must be a string",
    "string_too_short": "must have at least {min_length} characters",
    "string_too_long": "must have at most {max_length} characters",
    "string_pattern_mismatch": "has an invalid format",
    "too_short": "must have at least {min_length} items",
    "too_long": "must have at most {max_length} items",
    "list_type": "must be a list",
    "dict_type": "must be an object",
    "model_type": "must be an object",
    "model_attributes_type": "must be an object",
    "literal_error": "is not one of the allowed values",
    "enum": "is not one of the allowed values",
    "union_tag_invalid": "has an unknown type",
    "union_tag_not_found": "needs its type field",
    "date_type": "must be a date (YYYY-MM-DD)",
    "date_parsing": "must be a date (YYYY-MM-DD)",
    "date_from_datetime_parsing": "must be a date (YYYY-MM-DD)",
    "date_from_datetime_inexact": "must be a date (YYYY-MM-DD)",
    "datetime_type": "must be a date and time (ISO 8601)",
    "datetime_parsing": "must be a date and time (ISO 8601)",
    "datetime_from_date_parsing": "must be a date and time (ISO 8601)",
    "timezone_aware": "must include a time zone",
    "uuid_type": "must be a UUID",
    "uuid_parsing": "must be a UUID",
    "url_type": "must be a valid URL",
    "url_parsing": "must be a valid URL",
    "greater_than": "must be greater than {gt}",
    "greater_than_equal": "must be at least {ge}",
    "less_than": "must be less than {lt}",
    "less_than_equal": "must be at most {le}",
    "multiple_of": "must be a multiple of {multiple_of}",
}
# Only limits from the schema (not the input) may fill the texts above.
_SCHEMA_LIMITS = frozenset({"min_length", "max_length", "gt", "ge", "lt", "le", "multiple_of"})
_LOCATIONS = frozenset({"body", "query", "path", "header", "cookie"})
_MAX_LISTED_ERRORS = 5
_MAX_PATH_LENGTH = 120


def _error_text(error: Mapping[str, Any]) -> str:
    template = _TEXTS.get(str(error.get("type")), "is invalid")  # value_error, assertion_error…
    limits = {k: str(v)[:32] for k, v in (error.get("ctx") or {}).items() if k in _SCHEMA_LIMITS}
    try:
        return template.format(**limits)
    except (KeyError, IndexError, ValueError):
        return "is invalid"


def _unwrap(annotation: Any) -> Any:
    """`X` from `Annotated[X, …]` and `X | None`; a real union stays a union."""
    while True:
        origin = get_origin(annotation)
        if origin is Annotated:
            annotation = get_args(annotation)[0]
            continue
        if origin in (Union, UnionType):
            members = [arg for arg in get_args(annotation) if arg is not type(None)]
            if len(members) == 1:
                annotation = members[0]
                continue
        return annotation


def _step(current: Any, segment: Any, error_type: str, last: bool) -> tuple[str | None, Any]:
    """How to show one `loc` segment (None: drop it), and the annotation below it."""
    if isinstance(segment, int):
        args = get_args(_unwrap(current))
        return str(segment), args[0] if args else None  # a list index (or a JSON position)
    current = _unwrap(current)
    unknown = "<extra>" if error_type == "extra_forbidden" and last else "<…>"
    if isinstance(current, dict):  # the route's declared parameters
        return (segment, current[segment]) if segment in current else (unknown, None)
    if isinstance(current, type) and issubclass(current, BaseModel):
        for name, field in current.model_fields.items():
            if segment in (name, field.alias):
                return segment, field.annotation
        return unknown, None
    origin = get_origin(current)
    if origin in (dict, Mapping) or (isinstance(origin, type) and issubclass(origin, Mapping)):
        args = get_args(current)
        return "<key>", args[1] if len(args) == 2 else None  # a client-chosen key
    if origin in (Union, UnionType):
        return None, None  # a union member's label ("int", a validator's name, a tag)
    return "<…>", None


def _error_path(error: Mapping[str, Any], route: object) -> str:
    """`body.items.0.price`: the declared names only; anything the client chose is a placeholder."""
    loc = list(error.get("loc") or ())
    if not loc or loc[0] not in _LOCATIONS:
        return "request"
    where, rest = str(loc[0]), loc[1:]
    params = list(getattr(getattr(route, "dependant", None), f"{where}_params", None) or [])
    flat_body = where == "body" and len(params) == 1
    if flat_body and not getattr(params[0].field_info, "embed", False):
        current: Any = params[0].field_info.annotation  # FastAPI drops the parameter's name
    else:
        current = {param.alias: param.field_info.annotation for param in params}
    labels = [where]
    for index, segment in enumerate(rest):
        label, current = _step(current, segment, str(error.get("type")), index == len(rest) - 1)
        if label is not None:
            labels.append(label)
    path = ".".join(labels)
    return path if len(path) <= _MAX_PATH_LENGTH else path[: _MAX_PATH_LENGTH - 1] + "…"


def _validation_message(exc: RequestValidationError, route: object) -> str:
    entries = [f"{_error_path(e, route)}: {_error_text(e)}" for e in exc.errors()]
    unique = list(dict.fromkeys(entries))  # a union reports one error per member
    message = "; ".join(unique[:_MAX_LISTED_ERRORS])
    hidden = len(unique) - _MAX_LISTED_ERRORS
    return f"{message} (and {hidden} more)" if hidden > 0 else message


# ── 405: every method the path allows ────────────────────────────────────────────────────────


def _methods_at(routes: Sequence[BaseRoute], scope: Scope, candidates: frozenset[str]) -> set[str]:
    methods: set[str] = set()
    for route in routes:
        match, child_scope = route.matches(scope)
        if match is Match.NONE:
            continue
        if isinstance(route, Mount):  # a mounted router: look inside, with its rewritten scope
            methods |= _methods_at(route.routes, {**scope, **child_scope}, candidates)
        elif (declared := getattr(route, "methods", None)) is not None:
            methods |= set(declared)
        else:  # e.g. FastAPI's included routers: ask them method by method
            for method in candidates:
                if route.matches({**scope, "method": method})[0] is Match.FULL:
                    methods.add(method)
    return methods


def _allowed_methods(request: Request) -> set[str]:
    """Starlette's own `Allow` lists only the first matching route's methods, e.g. "HEAD" alone
    when GET and HEAD are separate routes; RFC 9110 wants them all."""
    candidates = set(_STANDARD_METHODS)
    for context in iter_route_contexts(request.app.routes):  # incl. custom ones, e.g. QUERY
        candidates |= getattr(context.original_route, "methods", None) or set()
    # Inside a Mount the scope was rewritten (root_path = the mount's prefix): match from the top.
    root_path = request.scope.get("app_root_path", request.scope.get("root_path", ""))
    top_scope = {**request.scope, "root_path": root_path}
    return _methods_at(request.app.router.routes, top_scope, frozenset(candidates))


# ── a DomainError raised outside the router (in middleware) ──────────────────────────────────


class DomainErrorMiddleware:
    """Answers a `DomainError` raised in middleware like the handlers do inside the router.
    Keep it outermost among the user middleware (`outermost_first`)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        finished = False

        async def tracking_send(message: Message) -> None:
            nonlocal finished
            if message["type"] in {"http.response.start", "websocket.close"}:
                finished = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except DomainError as exc:
            if finished:  # too late to answer: let the server deal with it
                raise
            if scope["type"] == "websocket":
                close = {"type": "websocket.close", "code": _close_code(exc.status)}
                await send({**close, "reason": exc.code})
            else:
                response = _envelope(exc.status, exc.code, exc.message, exc.headers)
                await response(scope, receive, send)


def _is_ours(middleware: Middleware) -> bool:
    return getattr(middleware, "cls", None) is DomainErrorMiddleware


def outermost_first(middleware: Sequence[Middleware]) -> list[Middleware]:
    """`middleware` with DomainErrorMiddleware first (= outermost), the rest in their order."""
    return [m for m in middleware if _is_ours(m)] + [m for m in middleware if not _is_ours(m)]


# ── installing ───────────────────────────────────────────────────────────────────────────────


def install_error_handlers(app: FastAPI) -> None:
    """Send every error as the envelope. Safe to call again (the handlers are replaced)."""
    if not any(_is_ours(m) for m in app.user_middleware):
        app.add_middleware(DomainErrorMiddleware)

    @app.exception_handler(DomainError)
    async def domain_error(conn: HTTPConnection, exc: DomainError) -> Response | None:
        return await _reply(conn, exc.status, exc.code, exc.message, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> Response:
        return _envelope(
            422, "validation_error", _validation_message(exc, request.scope.get("route"))
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(conn: HTTPConnection, exc: StarletteHTTPException) -> Response | None:
        code = _CODES_BY_STATUS.get(exc.status_code, f"http_{exc.status_code}")
        detail = exc.detail if isinstance(exc.detail, str) else None  # never a structure
        message = detail or _phrase(exc.status_code)
        headers = exc.headers
        if exc.status_code == 405 and isinstance(conn, Request):
            allowed = _allowed_methods(conn)
            if allowed and conn.method not in allowed:  # the router refused the method; a
                # handler that raised 405 itself (its method matched) keeps its own Allow
                headers = {**(headers or {}), "Allow": ", ".join(sorted(allowed))}
        return await _reply(conn, exc.status_code, code, message, headers)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> Response:
        # No logging here: Starlette re-raises after sending this, and the server (uvicorn)
        # logs the traceback once (F1.5 turns it into one redacted JSON line).
        return _envelope(500, "internal_error", _INTERNAL_ERROR_MESSAGE)
