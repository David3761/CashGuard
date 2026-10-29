"""F1.5: JSON log lines with secrets redacted (happy-path tests, fast mode)."""

import json
import logging
from decimal import Decimal
from typing import Any

import pytest
from pydantic import SecretStr

from app.config import Settings
from app.logging import JsonFormatter, configure_logging, redact

KEY = "sk-" + "ant-api03-abcdefghijklmnop"  # split, so the security grep (D6) finds no fakes
JWT = "eyJ" + "hbGciOiJSUzI1NiJ9." + "eyJzdWIiOiJtYXRlaSJ9." + "c2lnbmF0dXJl"  # split, as above
# AWS and Bedrock key shapes and an IBAN, all fake and split the same way (no scanner hits).
AWS_KEY_ID = "AKIA" + "X" * 16
AWS_SESSION_KEY_ID = "ASIA" + "Q" * 16
BEDROCK_KEY = "ABSK" + "QmVkcm9ja0FQSUtleS1mYWtl" * 2
BEDROCK_SHORT_KEY = "bedrock-" + "api-key-" + "YmVkcm9jay5hbWF6b25hd3MuY29t"
IBAN = "RO49" + "AAAA" + "1B31007593840000"
IBAN_GROUPED = "RO49 " + "AAAA 1B31 0075 9384 0000"


def _lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    return [json.loads(line) for line in capsys.readouterr().err.splitlines() if line]


def test_a_record_is_one_json_line_with_utc_time_and_extras(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")

    logging.getLogger("app.test").info(
        "Tranzacție la Mega Image: ăîșț", extra={"user_id": 7, "amount": Decimal("31.20")}
    )

    (line,) = _lines(capsys)
    assert line["level"] == "INFO"
    assert line["logger"] == "app.test"
    assert line["msg"] == "Tranzacție la Mega Image: ăîșț"
    assert line["ts"].endswith("Z")
    assert (line["user_id"], line["amount"]) == (7, "31.20")


def test_an_exception_goes_into_exc(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        logging.getLogger("app.test").exception("failed")

    (line,) = _lines(capsys)
    assert "Traceback" in line["exc"]
    assert "RuntimeError: boom" in line["exc"]


@pytest.mark.parametrize(
    "secret",
    [KEY, f"Bearer {JWT}", JWT, "postgresql+psycopg://app:db-pass-123@db:5432/app"],
)
def test_secrets_are_redacted_everywhere(capsys: pytest.CaptureFixture[str], secret: str) -> None:
    configure_logging("INFO")
    logger = logging.getLogger("app.test")

    logger.info("in the message: %s", secret, extra={"nested": {"value": [secret]}})
    try:
        raise ValueError(f"in the exception: {secret}")
    except ValueError:
        logger.exception("failed")

    output = json.dumps(_lines(capsys))
    assert "db-pass-123" not in output
    assert "abcdefghijklmnop" not in output
    assert "c2lnbmF0dXJl" not in output
    assert "[REDACTED]" in output


def test_a_logged_settings_dump_shows_no_secret(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("INFO")
    settings = Settings(_env_file=None, ANTHROPIC_API_KEY=SecretStr(KEY))

    logging.getLogger("app.test").info("%s", settings, extra={"settings": settings.model_dump()})

    assert KEY not in capsys.readouterr().err


def test_configuring_twice_keeps_one_handler_and_filters_by_level(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging("INFO")
    configure_logging("WARNING")
    logger = logging.getLogger("app.test")

    logger.info("dropped")
    logger.warning("kept")

    assert [line["msg"] for line in _lines(capsys)] == ["kept"]
    assert sum(isinstance(h.formatter, JsonFormatter) for h in logging.getLogger().handlers) == 1


def test_the_sdk_loggers_stay_at_warning_even_in_debug(capsys: pytest.CaptureFixture[str]) -> None:
    # The anthropic SDK logs full request bodies (user financial data) at DEBUG.
    configure_logging("DEBUG")

    for name in ("anthropic", "httpx", "httpx2", "httpcore"):
        logging.getLogger(name).debug("request body: SECRET")
        assert logging.getLogger(name).level == logging.WARNING

    assert "SECRET" not in capsys.readouterr().err


def test_uvicorn_loggers_flow_into_the_json_handler(capsys: pytest.CaptureFixture[str]) -> None:
    access = logging.getLogger("uvicorn.access")
    access.addHandler(logging.StreamHandler())  # as uvicorn's own config leaves it
    access.propagate = False
    configure_logging("INFO")

    access.info('%s - "GET /ws?token=%s HTTP/1.1" 101', "127.0.0.1", JWT)

    (line,) = _lines(capsys)
    assert line["logger"] == "uvicorn.access"
    assert JWT not in line["msg"]
    assert redact("plain text 1234.56") == "plain text 1234.56"


@pytest.mark.parametrize(
    "secret",
    [AWS_KEY_ID, AWS_SESSION_KEY_ID, BEDROCK_KEY, BEDROCK_SHORT_KEY, IBAN, IBAN_GROUPED],
    ids=["aws key id", "aws session key id", "bedrock key", "bedrock short key", "iban", "iban 4s"],
)
def test_aws_and_bedrock_keys_and_ibans_are_redacted(
    capsys: pytest.CaptureFixture[str], secret: str
) -> None:
    configure_logging("INFO")
    logger = logging.getLogger("app.test")

    logger.info("in the message: %s.", secret, extra={"nested": {"value": [secret]}})
    try:
        raise ValueError(f"in the exception: {secret}")
    except ValueError:
        logger.exception("failed")

    output = json.dumps(_lines(capsys))
    assert secret not in output
    assert secret.replace(" ", "")[6:14] not in output  # no tail of it either
    assert output.count("[REDACTED]") == 3


def test_redaction_leaves_ordinary_log_text_alone() -> None:
    for text in (
        "Claude call: model=us.anthropic.claude-sonnet-5-5 stop_reason=end_turn",
        "request_id=req_011CVabcdef tool annotate_transaction failed",
        "HTTP 429, rate_limit_error; 1500 lei on RO day 15",
    ):
        assert redact(text) == text
