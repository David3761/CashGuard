"""JSON logging (F1.5): one JSON object per line on stderr, secrets redacted.

Each line has `ts` (UTC, `…Z`, the real wall time even in SIM_MODE), `level`, `logger`, `msg`,
any `extra=` fields, and `exc` (the traceback). Redaction runs on all of them: Anthropic keys,
Bearer tokens, JWTs (e.g. the WebSocket `?token=` uvicorn logs), passwords in URLs, AWS access
key ids (AKIA…/ASIA…), Amazon Bedrock API keys (long-term ABSK…, short-term bedrock-api-key-…)
and IBANs (compact or in groups of 4, as in the snapshot's scrub).
`create_app()` calls `configure_logging`; command-line tools call it themselves.
"""

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any, TextIO

REDACTED = "[REDACTED]"
_PATTERNS = (
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]+"), REDACTED),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=\-]+"), rf"\1{REDACTED}"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]{5,}\.[A-Za-z0-9_\-]*"), REDACTED),
    (re.compile(r"([a-z][a-z0-9+.\-]*://[^:/@\s\"']+:)[^@\s\"']+@"), rf"\1{REDACTED}@"),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), REDACTED),
    (re.compile(r"\bABSK[A-Za-z0-9+/=]{16,}"), REDACTED),
    (re.compile(r"\bbedrock-api-key-[A-Za-z0-9+/=._\-]{8,}"), REDACTED),
    (
        re.compile(
            r"\b[A-Z]{2}\d{2}(?:[A-Z0-9]{11,30}|(?: [A-Z0-9]{4}){3,7}(?: [A-Z0-9]{1,4})?)\b"
        ),
        REDACTED,
    ),
)
# The anthropic SDK (and its HTTP stack) logs full request bodies at DEBUG: user financial data.
_QUIET_LOGGERS = ("anthropic", "httpx", "httpx2", "httpcore")
_UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")
_RECORD_FIELDS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "color_message",  # uvicorn's ANSI copy of msg
    "taskName",
}


def redact(text: str) -> str:
    """`text` with secrets replaced by [REDACTED] (also usable for audit rows, B15)."""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _jsonable(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    try:
        return redact(str(value))  # Decimal, date, SecretStr ('**********'), …
    except Exception:  # a broken __str__ must not lose the log line
        return "<unprintable>"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):  # e.g. logger.info("%s %s", 1)
            message = f"{record.msg} {record.args}"
        ts = datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds")
        payload: dict[str, Any] = {
            "ts": ts.replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(message),
        }
        for key, value in record.__dict__.items():
            if key not in _RECORD_FIELDS and key not in payload:
                payload[key] = _jsonable(value)
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


class _JsonHandler(logging.StreamHandler[TextIO]):
    """Writes to the *current* sys.stderr (pytest swaps it between tests)."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)


def configure_logging(level: str) -> None:
    """JSON lines on stderr at `level`. Safe to call again: it replaces only its own handler."""
    numeric = logging.getLevelNamesMapping().get(level.upper())
    if numeric is None:
        raise ValueError(f"unknown log level {level!r}")
    root = logging.getLogger()
    for handler in [h for h in root.handlers if isinstance(h, _JsonHandler)]:
        root.removeHandler(handler)
    handler = _JsonHandler()
    handler.setFormatter(JsonFormatter())
    handler.setLevel(numeric)
    root.addHandler(handler)
    root.setLevel(numeric)
    for name in _UVICORN_LOGGERS:  # uvicorn's own handlers go; its records flow to ours
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    for name in _QUIET_LOGGERS:
        logging.getLogger(name).setLevel(max(numeric, logging.WARNING))
