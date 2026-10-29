"""F1.4: every non-2xx response is the arch 9.1 envelope `{"error": {"code", "message"}}`.

The test-only routes live on an app built by the real `create_app()`, so the real wiring is tested.
Every `SECRET…` marker below is something a client sent or an internal name: it must never come
back in a response.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Annotated, Any, Literal

import httpx
import pytest
from fastapi import APIRouter, FastAPI, HTTPException, Query, Request, WebSocket
from fastapi.exceptions import RequestValidationError
from fastapi.responses import Response
from fastapi.testclient import TestClient
from pydantic import AfterValidator, BaseModel, ConfigDict, Field
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.routing import Route, Router
from starlette.types import ASGIApp, Message, Receive, Scope, Send
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.errors import DomainError, ErrorEnvelope, install_error_handlers
from app.main import create_app
from tests.conftest import MakeClient

pytestmark = pytest.mark.api


class Payment(BaseModel):
    amount: int
    iban: str = Field(max_length=10)


def _secret_check(value: str) -> str:
    raise ValueError(f"bad value {value}")  # a validator that quotes its input


class Cat(BaseModel):
    kind: Literal["cat"]
    meow: int


class Dog(BaseModel):
    kind: Literal["dog"]
    bark: int


class Colour(Enum):
    RED = "red"


class Secrets(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pet: Annotated[Cat | Dog, Field(discriminator="kind")] | None = None
    uid: uuid.UUID | None = None
    checked: Annotated[str, AfterValidator(_secret_check)] | None = None
    counts: dict[str, int] | None = None
    choice: Literal["a", "b"] | None = None
    slug: Annotated[str, Field(pattern=r"^[a-z]+$")] | None = None
    colour: Colour | None = None
    either: Annotated[str, AfterValidator(_secret_check)] | int | None = None
    twice: int | Annotated[int, Field(multiple_of=5)] | None = None  # both members fail alike


def _app(settings: Settings) -> FastAPI:
    application = create_app(settings)

    @application.get("/test/busy")
    async def busy() -> None:
        raise DomainError(
            "agent_busy",
            "The assistant is still answering your previous message.",
            status=409,
            headers={"Retry-After": "5"},
        )

    @application.get("/test/default-status")
    async def default_status() -> None:
        raise DomainError("x_code", "Something specific went wrong.")

    @application.get("/test/token")
    async def token() -> None:
        raise DomainError(
            "missing_token",
            "Send an access token.",
            status=401,
            headers={"WWW-Authenticate": "Bearer"},
        )

    @application.get("/test/diacritics")
    async def diacritics() -> None:
        raise DomainError("not_found", "Tranzacția nu există: ăîșț ĂÎȘȚ", status=404)

    @application.get("/test/subclass")
    async def subclass() -> None:
        class NotFound(DomainError):
            pass

        raise NotFound("not_found", "Goal not found.", status=404)

    @application.post("/test/payments")
    async def payments(payment: Payment) -> dict[str, int]:
        return {"amount": payment.amount}

    @application.post("/test/secrets")
    async def secrets(body: Secrets, q: Annotated[int, Query()] = 0) -> dict[str, int]:
        return {"q": q}

    @application.get("/test/search")
    async def search(
        a: Annotated[int, Query()],
        b: Annotated[int, Query()],
        c: Annotated[int, Query()],
        d: Annotated[int, Query()],
        e: Annotated[int, Query()],
        f: Annotated[int, Query()],
        g: Annotated[int, Query()],
    ) -> dict[str, int]:
        return {"sum": a + b + c + d + e + f + g}

    @application.get("/test/boom")
    async def boom() -> None:
        raise RuntimeError("SECRET-detail")

    @application.get("/test/teapot")
    async def teapot() -> None:
        raise HTTPException(status_code=418, detail="teapot")

    @application.get("/test/teapot-dict")
    async def teapot_dict() -> None:
        raise HTTPException(status_code=418, detail={"internal": "SECRET-structure"})

    @application.get("/test/unknown-status")
    async def unknown_status() -> None:
        raise HTTPException(status_code=499, detail={"internal": "SECRET-structure"})

    @application.get("/test/not-modified")
    async def not_modified() -> None:
        raise HTTPException(status_code=304)

    @application.put("/test/locked")
    async def locked() -> None:
        # the handler itself refuses, and says what is allowed
        raise HTTPException(status_code=405, headers={"Allow": "GET"})

    @application.api_route("/test/query-only", methods=["QUERY"])
    async def query_only() -> dict[str, str]:
        return {"ok": "yes"}

    # Two routes on one path inside an included router: Starlette alone would list one.
    included = APIRouter(prefix="/test/router")

    @included.api_route("/two-methods", methods=["QUERY"])
    async def routed_query() -> dict[str, str]:
        return {"ok": "yes"}

    @included.put("/two-methods")
    async def routed_put() -> dict[str, str]:
        return {"ok": "yes"}

    application.include_router(included)

    async def mounted(request: Request) -> Response:
        return Response("mounted")

    # Two routes on one mounted path: Starlette's own Allow would list only the first one's.
    application.mount(
        "/test/sub",
        Router(
            routes=[Route("/r", mounted, methods=["GET"]), Route("/r", mounted, methods=["PUT"])]
        ),
    )

    @application.get("/test/hand-made-validation")
    async def hand_made_validation() -> None:
        raise RequestValidationError(
            [
                {"type": "greater_than", "loc": ("body", "x"), "msg": "SECRET", "input": "SECRET"},
                {"type": "missing", "loc": ("SECRET_LOC", "y"), "msg": "SECRET", "input": None},
                {"type": "missing", "loc": ("body", *range(60)), "msg": "SECRET", "input": None},
            ]
        )

    @application.websocket("/test/ws-busy")
    async def ws_busy(websocket: WebSocket) -> None:
        await websocket.accept()
        raise DomainError("agent_busy", "SECRET still answering.", status=409)

    @application.websocket("/test/ws-early")
    async def ws_early(websocket: WebSocket) -> None:
        raise DomainError("missing_token", "SECRET no token.", status=401)

    @application.websocket("/test/ws-broken")
    async def ws_broken(websocket: WebSocket) -> None:
        await websocket.accept()
        raise DomainError("sim_failed", "SECRET the simulator broke.", status=503)

    return application


def assert_envelope(response: httpx.Response, status: int, code: str) -> str:
    """The response is the envelope with this status and code; returns its message."""
    assert response.status_code == status
    assert response.headers["content-type"] == "application/json"
    envelope = ErrorEnvelope.model_validate_json(response.content)
    assert envelope.error.code == code
    assert set(response.json()) == {"error"}
    assert "SECRET" not in response.text
    return envelope.error.message


# ── DomainError ──────────────────────────────────────────────────────────────────────────────


async def test_domain_error_gives_its_status_headers_and_envelope(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/busy")

    message = assert_envelope(response, 409, "agent_busy")
    assert message == "The assistant is still answering your previous message."
    assert response.headers["retry-after"] == "5"


async def test_domain_error_401_carries_www_authenticate(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/token")

    assert_envelope(response, 401, "missing_token")
    assert response.headers["www-authenticate"] == "Bearer"


async def test_domain_error_defaults_to_400(settings: Settings, make_client: MakeClient) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/default-status")

    assert_envelope(response, 400, "x_code")


async def test_domain_error_subclasses_get_the_envelope(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/subclass")

    assert_envelope(response, 404, "not_found")


async def test_messages_keep_romanian_diacritics(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/diacritics")

    assert assert_envelope(response, 404, "not_found") == "Tranzacția nu există: ăîșț ĂÎȘȚ"
    assert "Tranzacția".encode() in response.content  # raw UTF-8, not \\u escapes


# ── DomainError outside the router: middleware ───────────────────────────────────────────────


class _GateMiddleware(BaseHTTPMiddleware):
    """Like a future auth / agent_busy gate (B5, B9): refuses before the route runs."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path == "/test/gated":
            raise DomainError("agent_busy", "Still answering.", status=409)
        return await call_next(request)


class _PureGateMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in {"http", "websocket"} and scope["path"].startswith("/test/pure-gated"):
            raise DomainError("missing_token", "Send an access token.", status=401)
        await self.app(scope, receive, send)


class _StampMiddleware(BaseHTTPMiddleware):
    """Like CORS: adds a header to every response, error responses included."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Stamp"] = "1"
        return response


async def test_a_domain_error_from_a_route_passes_through_the_middleware(
    settings: Settings, make_client: MakeClient
) -> None:
    # Answered inside the router, so every middleware sees (and may decorate) the error response.
    application = _app(settings)
    application.add_middleware(_StampMiddleware)

    async with make_client(application) as client:
        response = await client.get("/test/busy")

    assert_envelope(response, 409, "agent_busy")
    assert response.headers["x-stamp"] == "1"


@pytest.mark.parametrize("middleware", [_GateMiddleware, _PureGateMiddleware])
async def test_a_domain_error_raised_in_middleware_gets_its_status(
    settings: Settings, make_client: MakeClient, middleware: Any
) -> None:
    # Added after create_app(), as teammates will: it ends up outside the router's handlers.
    application = _app(settings)
    application.add_middleware(middleware)
    path = "/test/gated" if middleware is _GateMiddleware else "/test/pure-gated"

    async with make_client(application) as client:  # nothing may escape as an exception
        response = await client.get(path)
        after = await client.get("/api/health")

    expected = (409, "agent_busy") if middleware is _GateMiddleware else (401, "missing_token")
    assert_envelope(response, *expected)
    assert after.status_code == 200


class _LateGateMiddleware:
    """Sends a response, then raises: too late to answer with the envelope."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"] == "/test/late":
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"sent"})
            raise DomainError("agent_busy", "Too late.", status=409)
        await self.app(scope, receive, send)


async def test_a_domain_error_after_the_response_started_is_left_to_the_server(
    settings: Settings,
) -> None:
    # Called as raw ASGI to see every message: a second response must never be started.
    application = _app(settings)
    application.add_middleware(_LateGateMiddleware)
    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/test/late",
        "raw_path": b"/test/late",
        "root_path": "",
        "query_string": b"",
        "headers": [],
        "server": ("test", 80),
        "client": ("client", 1234),
    }

    with pytest.raises(DomainError):
        await application(scope, receive, send)

    assert [message["type"] for message in sent] == ["http.response.start", "http.response.body"]


def test_a_domain_error_raised_in_middleware_closes_a_websocket(settings: Settings) -> None:
    application = _app(settings)
    application.add_middleware(_PureGateMiddleware)

    with (
        TestClient(application) as client,
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect("/test/pure-gated-ws"),
    ):
        pass  # pragma: no cover - the connection is refused

    assert (closed.value.code, closed.value.reason) == (1008, "missing_token")


# ── DomainError on a WebSocket ───────────────────────────────────────────────────────────────


def test_a_domain_error_on_an_open_websocket_closes_it_with_its_code(settings: Settings) -> None:
    with (
        TestClient(_app(settings)) as client,
        client.websocket_connect("/test/ws-busy") as websocket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        websocket.receive_text()

    # 1008 = policy violation (arch 5.1 uses it for a bad token); the reason is only the code.
    assert (closed.value.code, closed.value.reason) == (1008, "agent_busy")


def test_a_domain_error_before_accept_refuses_the_websocket(settings: Settings) -> None:
    with (
        TestClient(_app(settings)) as client,
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect("/test/ws-early"),
    ):
        pass  # pragma: no cover - the connection is refused

    assert (closed.value.code, closed.value.reason) == (1008, "missing_token")


def test_a_5xx_domain_error_closes_the_websocket_as_an_internal_error(settings: Settings) -> None:
    with (
        TestClient(_app(settings)) as client,
        client.websocket_connect("/test/ws-broken") as websocket,
        pytest.raises(WebSocketDisconnect) as closed,
    ):
        websocket.receive_text()

    assert (closed.value.code, closed.value.reason) == (1011, "sim_failed")


# ── routing errors ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/api/nope", "/nope"])
async def test_an_unknown_route_is_not_found(
    settings: Settings, make_client: MakeClient, path: str
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get(path)

    assert_envelope(response, 404, "not_found")


@pytest.mark.parametrize(
    ("method", "path", "allow"),
    [
        # GET and HEAD are separate routes: Starlette alone would say only "HEAD"
        ("POST", "/api/health", "GET, HEAD"),
        # a custom method is listed too, also inside an included router
        ("GET", "/test/query-only", "QUERY"),
        ("GET", "/test/router/two-methods", "PUT, QUERY"),
        # inside a mounted router (the scope is rewritten there), both of its routes
        ("POST", "/test/sub/r", "GET, HEAD, PUT"),
    ],
)
async def test_a_wrong_method_says_every_method_the_path_allows(
    settings: Settings, make_client: MakeClient, method: str, path: str, allow: str
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.request(method, path)

    assert_envelope(response, 405, "method_not_allowed")
    assert response.headers["allow"] == allow


async def test_a_405_raised_by_a_handler_keeps_its_own_allow(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.put("/test/locked")

    assert_envelope(response, 405, "method_not_allowed")
    assert response.headers["allow"] == "GET"


async def test_head_and_get_on_health_still_work(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        head = await client.head("/api/health")
        get = await client.get("/api/health")

    assert (head.status_code, head.content) == (200, b"")
    assert (get.status_code, get.json()) == (200, {"status": "ok"})


# ── validation errors ────────────────────────────────────────────────────────────────────────


async def test_malformed_json_is_a_validation_error(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.post(
            "/test/payments",
            content=b'{"SECRET_JSON": 12,',
            headers={"content-type": "application/json"},
        )

    message = assert_envelope(response, 422, "validation_error")
    assert message.startswith("body.")
    assert message.endswith(": invalid JSON")


async def test_a_missing_field_is_named(settings: Settings, make_client: MakeClient) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.post("/test/payments", json={"iban": "RO49"})

    assert assert_envelope(response, 422, "validation_error") == "body.amount: field required"


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        ({"amount": "abc-SECRET-INPUT", "iban": "RO49"}, "body.amount: must be an integer"),
        (
            {"amount": 1, "iban": "SECRET-RO49AAAA1B31007593840000"},
            "body.iban: must have at most 10 characters",
        ),
    ],
)
async def test_a_rejected_value_is_never_echoed_back(
    settings: Settings, make_client: MakeClient, sent: dict[str, Any], expected: str
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.post("/test/payments", json=sent)

    assert assert_envelope(response, 422, "validation_error") == expected


@pytest.mark.parametrize(
    ("sent", "expected"),
    [
        # pydantic's own messages for these quote the input or internal names
        ({"pet": {"kind": "SECRET_TAG"}}, "body.pet: has an unknown type"),
        ({"uid": "SECRET-UUID"}, "body.uid: must be a UUID"),
        ({"checked": "SECRET_VALUE"}, "body.checked: is invalid"),
        ({"counts": {"SECRET_KEY": "x"}}, "body.counts.<key>: must be an integer"),
        ({"SECRET_EXTRA_KEY": 1}, "body.<extra>: unknown field"),
        ({"choice": "SECRET_CHOICE"}, "body.choice: is not one of the allowed values"),
        ({"slug": "SECRET_SLUG"}, "body.slug: has an invalid format"),
        ({"colour": "SECRET_COLOUR"}, "body.colour: is not one of the allowed values"),
        ({"either": "SECRET_EITHER"}, "body.either: is invalid; body.either: must be an integer"),
        ({"pet": {"kind": "cat", "meow": "SECRET_MEOW"}}, "body.pet.<…>: must be an integer"),
        ({"twice": "SECRET_TWICE"}, "body.twice: must be an integer"),  # said once
    ],
)
async def test_no_validation_message_quotes_what_was_sent(
    settings: Settings, make_client: MakeClient, sent: dict[str, Any], expected: str
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.post("/test/secrets", json=sent)

    assert assert_envelope(response, 422, "validation_error") == expected
    assert "_secret_check" not in response.text  # no internal validator names


async def test_a_query_value_is_never_echoed_back(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.post("/test/secrets", params={"q": "SECRET_Q"}, json={})

    assert assert_envelope(response, 422, "validation_error") == "query.q: must be an integer"


async def test_a_huge_client_key_is_not_reflected(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.post("/test/secrets", json={"counts": {"K" * 1_000_000: "x"}})

    assert_envelope(response, 422, "validation_error")
    assert len(response.content) < 300


async def test_odd_validation_errors_still_give_safe_messages(
    settings: Settings, make_client: MakeClient
) -> None:
    # A limit missing from ctx, and a loc outside the request locations (hand-made errors). The
    # route declares no body, so `x` isn't a declared name either: a placeholder.
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/hand-made-validation")

    message = assert_envelope(response, 422, "validation_error")
    first, second, deep = message.split("; ")
    assert (first, second) == ("body.<…>: is invalid", "request: field required")
    path = deep.removesuffix(": field required")
    assert len(path) == 120  # capped
    assert path.startswith("body.0.1.2.")
    assert path.endswith("…")


async def test_query_errors_are_named_and_capped_at_five(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/search", params={"a": "x"})

    message = assert_envelope(response, 422, "validation_error")
    assert message.startswith("query.a: must be an integer; query.b: field required")
    assert message.count("query.") == 5
    assert message.endswith("(and 2 more)")


# ── other HTTP errors ────────────────────────────────────────────────────────────────────────


async def test_an_http_exception_keeps_its_text_detail(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/teapot")

    assert assert_envelope(response, 418, "http_418") == "teapot"


async def test_a_structured_http_exception_detail_is_not_exposed(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/teapot-dict")

    assert assert_envelope(response, 418, "http_418") == "I'm a Teapot"


async def test_a_status_python_does_not_know_still_gets_the_envelope(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/unknown-status")

    assert assert_envelope(response, 499, "http_499") == "Error"


async def test_a_status_without_a_body_stays_empty(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings)) as client:
        response = await client.get("/test/not-modified")

    assert response.status_code == 304
    assert response.content == b""


# ── unexpected errors ────────────────────────────────────────────────────────────────────────


async def test_an_unexpected_error_is_a_generic_500(
    settings: Settings, make_client: MakeClient
) -> None:
    # Starlette re-raises after sending the 500 (so the server logs the traceback); the client
    # must not re-raise it here, to see the response.
    async with make_client(_app(settings), raise_app_exceptions=False) as client:
        response = await client.get("/test/boom")
        after = await client.get("/api/health")

    message = assert_envelope(response, 500, "internal_error")
    assert message == "Something went wrong on our side. Please try again."
    for leak in ("Traceback", "RuntimeError", "boom"):
        assert leak not in response.text
    assert after.status_code == 200  # the app keeps serving


async def test_concurrent_failures_and_successes_stay_separate(
    settings: Settings, make_client: MakeClient
) -> None:
    async with make_client(_app(settings), raise_app_exceptions=False) as client:
        responses = await asyncio.gather(
            *(client.get("/test/boom" if i % 2 else "/api/health") for i in range(40))
        )

    for i, response in enumerate(responses):
        if i % 2:
            assert_envelope(response, 500, "internal_error")
        else:
            assert response.status_code == 200


async def test_installing_the_handlers_twice_changes_nothing(
    settings: Settings, make_client: MakeClient
) -> None:
    application = _app(settings)
    install_error_handlers(application)
    application.add_middleware(_GateMiddleware)

    async with make_client(application) as client:
        response = await client.get("/test/busy")
        gated = await client.get("/test/gated")

    assert_envelope(response, 409, "agent_busy")
    assert_envelope(gated, 409, "agent_busy")


# ── the documented contract ──────────────────────────────────────────────────────────────────


def test_openapi_documents_the_envelope_not_fastapis_422(settings: Settings) -> None:
    schema = _app(settings).openapi()

    payments = schema["paths"]["/test/payments"]["post"]["responses"]
    assert payments["default"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ErrorEnvelope"
    }
    assert "422" not in payments
    assert "HTTPValidationError" not in schema["components"]["schemas"]
    assert set(schema["components"]["schemas"]["ErrorBody"]["required"]) == {"code", "message"}
