"""JSON logs on stdout. Secrets are `SecretStr` in `Settings`; `redact()` also scrubs anything
that looks like an Anthropic key (and the configured key itself) from every log line and from
the error texts we store (B15)."""

import json
import logging
import re
import sys
from datetime import UTC, datetime

_KEY_PATTERN = re.compile(r"sk-ant-[A-Za-z0-9_\-]+")


def redact(text: str) -> str:
    from app.config import get_settings

    key = get_settings().ANTHROPIC_API_KEY
    if key is not None and key.get_secret_value():
        text = text.replace(key.get_secret_value(), "***")
    return _KEY_PATTERN.sub("sk-ant-***", text)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return redact(json.dumps(entry, ensure_ascii=False, default=str))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
