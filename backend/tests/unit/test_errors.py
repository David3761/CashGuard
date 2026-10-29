"""F1.4: `DomainError` and the arch 9.1 envelope model (the pure parts; handlers: tests/api)."""

import re

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from app.errors import DomainError, ErrorBody, ErrorEnvelope

SNAKE_CASE = r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*"


def test_domain_error_carries_code_message_and_status() -> None:
    error = DomainError("agent_busy", "The assistant is still answering.", status=409)

    assert (error.code, error.message, error.status) == (
        "agent_busy",
        "The assistant is still answering.",
        409,
    )
    assert str(error) == "The assistant is still answering."


def test_domain_error_defaults_to_400() -> None:
    assert DomainError("x_code", "Something specific went wrong.").status == 400


def test_domain_error_subclasses_keep_working() -> None:
    # Teammates may define e.g. NotFound(DomainError); the handler catches subclasses too.
    class NotFound(DomainError):
        def __init__(self, what: str) -> None:
            super().__init__("not_found", f"{what} not found.", status=404)

    assert NotFound("Goal").status == 404


@pytest.mark.parametrize("code", ["x", "agent_busy", "http_418", "a" * 64, "c4_step2"])
def test_domain_error_accepts_snake_case_codes(code: str) -> None:
    assert DomainError(code, "message").code == code


@pytest.mark.parametrize(
    "code",
    ["", "BadCode", "bad-code", "bad code", "_leading", "trailing_", "double__underscore",
     "9starts_with_digit", "a" * 65, "agent_busy\n"],
)  # fmt: skip
def test_domain_error_rejects_codes_that_are_not_snake_case(code: str) -> None:
    # Codes are a stable contract the app branches on (work-breakdown 0.3 rule 5).
    with pytest.raises(ValueError, match="code"):
        DomainError(code, "message")


@pytest.mark.parametrize("status", [400, 404, 422, 500, 599])
def test_domain_error_accepts_error_statuses(status: int) -> None:
    assert DomainError("x_code", "message", status=status).status == status


@pytest.mark.parametrize("status", [399, 200, 600, True, 400.0, "400"])
def test_domain_error_rejects_statuses_outside_400_to_599(status: object) -> None:
    with pytest.raises(ValueError, match="status"):
        DomainError("x_code", "message", status=status)  # type: ignore[arg-type]


@pytest.mark.parametrize("message", ["", "   ", None])
def test_domain_error_needs_a_message(message: object) -> None:
    # Messages must be clear enough for Claude or a developer to act on (how-we-work §5).
    with pytest.raises(ValueError, match="message"):
        DomainError("x_code", message)  # type: ignore[arg-type]


@given(code=st.from_regex(rf"\A{SNAKE_CASE}\Z").filter(lambda c: len(c) <= 64))
def test_any_snake_case_code_up_to_64_chars_is_accepted(code: str) -> None:
    assert DomainError(code, "message").code == code


@given(code=st.text(max_size=70))
def test_anything_else_is_rejected(code: str) -> None:
    if re.fullmatch(SNAKE_CASE, code) and len(code) <= 64:
        assert DomainError(code, "message").code == code
    else:
        with pytest.raises(ValueError, match="code"):
            DomainError(code, "message")


def test_the_envelope_has_exactly_the_arch_9_1_shape() -> None:
    envelope = ErrorEnvelope(error=ErrorBody(code="agent_busy", message="Still answering."))

    assert envelope.model_dump() == {"error": {"code": "agent_busy", "message": "Still answering."}}


def test_the_envelope_is_strict() -> None:
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"error": {"code": "x", "message": "m", "detail": "extra"}})
    with pytest.raises(ValidationError):
        ErrorEnvelope.model_validate({"error": {"code": "x"}})


def test_domain_error_carries_response_headers() -> None:
    # RFC 9110: a 401 needs WWW-Authenticate (B5); agent_busy can say when to retry.
    error = DomainError("agent_busy", "Still answering.", status=409, headers={"Retry-After": "5"})

    assert dict(error.headers) == {"Retry-After": "5"}
    assert DomainError("x_code", "message").headers == {}


def test_domain_error_headers_are_read_only() -> None:
    error = DomainError("x_code", "message", headers={"Retry-After": "5"})

    with pytest.raises(TypeError):
        error.headers["Retry-After"] = "0"  # type: ignore[index]


@pytest.mark.parametrize(
    "headers",
    [
        {"Retry-After": "5\r\nSet-Cookie: x=1"},  # header injection
        {"X-Evil\n": "1"},
        {"": "1"},
        {"Content-Length": "0"},  # the response sets these itself
        {"content-type": "text/html"},
        {"Retry-After": 5},
    ],
)
def test_domain_error_rejects_unsafe_headers(headers: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="header"):
        DomainError("x_code", "message", headers=headers)  # type: ignore[arg-type]
