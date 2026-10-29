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

    # Database: the driver is psycopg 3 (`postgresql+psycopg`). Ports are bomboe's compose (B1):
    # dev DB `db` on 5434, the throwaway test DB `db-test` on 5435 (5432/5433 are often taken).
    DATABASE_URL: SecretStr = SecretStr(
        "postgresql+psycopg://cashguard:cashguard@localhost:5434/cashguard"
    )
    TEST_DATABASE_URL: SecretStr = SecretStr(
        "postgresql+psycopg://cashguard:cashguard@localhost:5435/cashguard_test"
    )
    # Claude (arch 6.8)
    ANTHROPIC_API_KEY: SecretStr | None = None
    ANTHROPIC_MODEL: str = Field(default="claude-sonnet-5-5", min_length=1)
    ANTHROPIC_EFFORT: Effort = "low"
    ANTHROPIC_REFUSAL_FALLBACK: bool = False
    # Who serves Claude: the Claude API (ANTHROPIC_API_KEY) or Amazon Bedrock (the hackathon's
    # temporary AWS credentials below; ANTHROPIC_MODEL becomes `us.anthropic.<model>` there).
    LLM_PROVIDER: Literal["anthropic", "bedrock"] = "anthropic"
    AWS_DEFAULT_REGION: str | None = None
    # A Bedrock API key (console: Amazon Bedrock -> API keys). Wins over the AWS_* credentials.
    AWS_BEARER_TOKEN_BEDROCK: SecretStr | None = None
    AWS_ACCESS_KEY_ID: SecretStr | None = None
    AWS_SECRET_ACCESS_KEY: SecretStr | None = None
    AWS_SESSION_TOKEN: SecretStr | None = None
    # Keycloak (arch 5.1). Defaults = bomboe's local compose (Keycloak on host port 8081, B5).
    KEYCLOAK_ISSUER: str | None = "http://localhost:8081/realms/cashguard"
    KEYCLOAK_AUDIENCE: str | None = "cashguard-api"
    # Where the API fetches discovery/JWKS when it differs from the issuer (inside docker:
    # http://keycloak:8080/realms/cashguard).
    KEYCLOAK_INTERNAL_URL: str | None = None
    KEYCLOAK_CRON_CLIENT_SECRET: SecretStr | None = None
    # Demo and agent
    SIM_MODE: bool = False
    SIM_START_DATE: date = date(2026, 6, 15)
    # SIM_MODE only: load the simulator's date from the sim_clock table at startup (B10, A22).
    SIM_CLOCK_FROM_DB: bool = True
    MAX_AGENT_ITERATIONS: int = Field(default=6, ge=1, le=20)
    QUESTIONS_PER_DAY: int = Field(default=1, ge=1, le=10)
    LOG_LEVEL: LogLevel = "INFO"
    # Rate limits (app.security.ratelimit), per principal (user, or the app API's "app").
    RATE_LIMIT_CHAT_PER_MINUTE: int = Field(default=10, ge=1)
    RATE_LIMIT_CHAT_PER_DAY: int = Field(default=200, ge=1)
    RATE_LIMIT_SIM_PER_MINUTE: int = Field(default=5, ge=1)
    RATE_LIMIT_WS_CONNECT_PER_MINUTE: int = Field(default=10, ge=1)
    # The app API (David V.'s Flutter contract, API_SPEC.md): root routes, no auth, one demo user.
    APP_API_ENABLED: bool = False
    # The demo user: a users.keycloak_sub, or a numeric users.id. Default: Matei (realm + seed).
    APP_API_USER: str = Field(default="a0000000-0000-4000-8000-000000000001", min_length=1)
    APP_API_MAX_TEXT_CHARS: int = Field(default=2000, ge=1, le=10_000)
    APP_API_REPLY_TIMEOUT_S: float = Field(default=120.0, gt=0, le=600)
    APP_API_HISTORY_LIMIT: int = Field(default=100, ge=1, le=1000)
    APP_API_MAX_DEVICES: int = Field(default=5, ge=1, le=50)
    # CORS for Flutter web / browser debugging only (the native app sends no Origin).
    APP_API_CORS_ORIGIN_REGEX: str | None = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    # Push (FCM HTTP v1): the Firebase project's service-account JSON. Unset → pushes are logged
    # and skipped. Keep the file outside git.
    FCM_SERVICE_ACCOUNT_FILE: Path | None = None
    FCM_PROJECT_ID: str | None = None

    @field_validator(
        "ANTHROPIC_API_KEY",
        "AWS_DEFAULT_REGION",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "KEYCLOAK_ISSUER",
        "KEYCLOAK_AUDIENCE",
        "KEYCLOAK_INTERNAL_URL",
        "KEYCLOAK_CRON_CLIENT_SECRET",
        "APP_API_CORS_ORIGIN_REGEX",
        "FCM_SERVICE_ACCOUNT_FILE",
        "FCM_PROJECT_ID",
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

    @field_validator("ANTHROPIC_EFFORT", "LLM_PROVIDER", mode="before")
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

    @field_validator("KEYCLOAK_ISSUER", "KEYCLOAK_INTERNAL_URL")
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

    @field_validator("APP_API_CORS_ORIGIN_REGEX")
    @classmethod
    def _compiles(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as err:
                raise ValueError(f"must be a valid regular expression ({err})") from None
        return value

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
