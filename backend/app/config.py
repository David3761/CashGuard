"""App settings (F1.2): every environment variable the app reads (arch §3), from the env and
`backend/.env`.

- Field names are the env names (`settings.ANTHROPIC_MODEL`). The environment beats `.env`.
- Secrets are `SecretStr`: they never show in `repr`, `str` or `model_dump*`.
- An empty value means "not set", so the code default applies.
- `TZ` is deliberately not a setting: day boundaries are always Europe/Bucharest (`app.clock`).

Only `create_app()` and CLI entry points call `get_settings()`. Routes use
`Depends(get_app_settings)`; classes receive a `Settings`. Tests build `Settings(_env_file=None)`.
"""

import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import SplitResult, urlsplit

from fastapi import Request
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

Effort = Literal["low", "medium", "high", "xhigh", "max"]  # Sonnet 5.5's levels (arch 6.8)
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_REALM_PATH = re.compile(r"(?:/[^/]+)*/realms/[^/]+/?")  # Keycloak: [/prefix]/realms/<realm>


def _parse_url(raw: str) -> SplitResult | None:
    """The URL's parts, or None if it can't be parsed or its port isn't a valid number."""
    try:
        url = urlsplit(raw)
        _ = url.port  # raises ValueError for "host:abc" or a port out of range
    except ValueError:
        return None
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",  # compose-only variables share the .env
        frozen=True,
        hide_input_in_errors=True,  # a rejected DATABASE_URL would otherwise print its password
    )

    # Database: the driver is psycopg 3 (`postgresql+psycopg`); the test DB is H-1's db-test.
    DATABASE_URL: SecretStr = SecretStr(
        "postgresql+psycopg://cashguard:cashguard@localhost:5432/cashguard"
    )
    TEST_DATABASE_URL: SecretStr = SecretStr(
        "postgresql+psycopg://cashguard_test:cashguard_test@localhost:5433/cashguard_test"
    )
    # Claude (arch 6.8)
    ANTHROPIC_API_KEY: SecretStr | None = None
    ANTHROPIC_MODEL: str = Field(default="claude-sonnet-5-5", min_length=1)
    ANTHROPIC_EFFORT: Effort = "low"
    ANTHROPIC_REFUSAL_FALLBACK: bool = False
    # Keycloak (arch 5.1)
    KEYCLOAK_ISSUER: str | None = None
    KEYCLOAK_AUDIENCE: str | None = None
    KEYCLOAK_CRON_CLIENT_SECRET: SecretStr | None = None
    # Demo and agent
    SIM_MODE: bool = False
    SIM_START_DATE: date = date(2026, 6, 15)
    MAX_AGENT_ITERATIONS: int = Field(default=6, ge=1, le=20)
    QUESTIONS_PER_DAY: int = Field(default=1, ge=1, le=10)
    LOG_LEVEL: LogLevel = "INFO"

    @field_validator(
        "ANTHROPIC_API_KEY",
        "KEYCLOAK_ISSUER",
        "KEYCLOAK_AUDIENCE",
        "KEYCLOAK_CRON_CLIENT_SECRET",
        mode="before",
    )
    @classmethod
    def _blank_means_unset(cls, value: object) -> object:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        return None if raw == "" else value

    @field_validator("DATABASE_URL", "TEST_DATABASE_URL", mode="before")
    @classmethod
    def _psycopg_url(cls, value: object) -> object:
        # Checked at startup: otherwise a wrong URL only fails at the first query.
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw, str):
            return value
        url = _parse_url(raw)
        if url is None or url.scheme != "postgresql+psycopg" or not url.hostname:
            raise ValueError("must be a postgresql+psycopg://user:password@host:port/db URL")
        if not url.path.strip("/"):
            raise ValueError("must name the database: postgresql+psycopg://…/db")
        return value

    @field_validator("ANTHROPIC_EFFORT", mode="before")
    @classmethod
    def _lower(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @field_validator("LOG_LEVEL", mode="before")
    @classmethod
    def _upper(cls, value: object) -> object:
        return value.upper() if isinstance(value, str) else value

    @field_validator("SIM_START_DATE", mode="before")
    @classmethod
    def _iso_date_only(cls, value: object) -> object:
        # pydantic alone would also read 1781481600 as a Unix timestamp and take a datetime.
        if isinstance(value, str) and _ISO_DATE.fullmatch(value):
            return value
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        raise ValueError("must be a date written as YYYY-MM-DD")

    @field_validator("KEYCLOAK_ISSUER")
    @classmethod
    def _issuer_is_a_realm_url(cls, value: str | None) -> str | None:
        # Tokens' `iss` is compared exactly (arch 5.1); Keycloak's never ends with "/".
        if value is None:
            return None
        url = _parse_url(value)
        if (
            url is None
            or url.scheme not in {"http", "https"}
            or not url.hostname
            or "?" in value
            or "#" in value
            or not _REALM_PATH.fullmatch(url.path)
        ):
            raise ValueError("must be the realm URL, e.g. http://localhost:8080/realms/cashguard")
        return value.rstrip("/")

    @field_validator("*", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        # One rule for every field: surrounding spaces never matter (also inside a SecretStr
        # passed in code). Defined last, so it runs before the other "before" validators:
        # pydantic runs them in reverse order. The other validators rely on it.
        if isinstance(value, SecretStr):
            return SecretStr(value.get_secret_value().strip())
        return value.strip() if isinstance(value, str) else value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings (env + `backend/.env`), built on first use."""
    return Settings()


def get_app_settings(request: Request) -> Settings:
    """FastAPI dependency: the settings `create_app()` stored on the app."""
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        raise RuntimeError("app.state.settings is missing: build the app with create_app()")
    return settings
