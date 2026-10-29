"""Application settings, read from the environment and `.env` (arch §3)."""

from datetime import date
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+psycopg://cashguard:cashguard@localhost:5434/cashguard"
    TEST_DATABASE_URL: str = (
        "postgresql+psycopg://cashguard:cashguard@localhost:5435/cashguard_test"
    )

    ANTHROPIC_API_KEY: SecretStr | None = None
    ANTHROPIC_MODEL: str = "claude-sonnet-5-5"
    ANTHROPIC_EFFORT: str = "low"

    KEYCLOAK_ISSUER: str = "http://localhost:8081/realms/cashguard"
    KEYCLOAK_AUDIENCE: str = "cashguard-api"
    # Where the API itself reaches the realm (discovery + JWKS); defaults to the issuer.
    # Locally in docker: http://keycloak:8080/realms/cashguard. Hosted: leave unset.
    KEYCLOAK_INTERNAL_URL: str | None = None

    SIM_MODE: bool = True
    SIM_START_DATE: date = date(2026, 6, 15)
    TZ: str = "Europe/Bucharest"
    # Load the sim date from the DB at startup (off in tests).
    SIM_CLOCK_FROM_DB: bool = True

    MAX_AGENT_ITERATIONS: int = 6
    QUESTIONS_PER_DAY: int = 1
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
