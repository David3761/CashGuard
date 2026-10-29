"""F1.2: Settings: defaults, env and .env sources, validation, secret masking, .env.example drift.

The autouse fixture in tests/conftest.py isolates every test from the developer's real
backend/.env and shell variables (tests/unit/test_isolation.py proves it).
"""

import re
import string
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from dotenv.parser import parse_stream
from hypothesis import given
from hypothesis import strategies as st
from pydantic import SecretStr, ValidationError

from app.config import BACKEND_DIR, Settings, get_settings

ENV_EXAMPLE = BACKEND_DIR / ".env.example"
# Anthropic keys start with this. Written split, so the security review's key grep (D6) finds
# only real leaks, never the fakes in these tests.
KEY_PREFIX = "sk-" + "ant-"
# Variables in .env.example that the app doesn't read (compose / cron only). bomboe's B1 adds its
# compose variables here (HANDOFFS H-5). Must stay disjoint from the Settings fields.
# Compose-only variables (bomboe's B1: the Keycloak container, the cron container's TZ).
NON_APP_KEYS: frozenset[str] = frozenset(
    {
        "KC_HOSTNAME",
        "KC_ADMIN_USER",
        "KC_ADMIN_PASSWORD",
        "KC_CRON_CLIENT_SECRET",
        "KC_DB_PASSWORD",
        "KC_DEMO_PASSWORD",
        "TZ",
    }
)

FIELDS = frozenset(
    {
        "DATABASE_URL",
        "TEST_DATABASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_MODEL",
        "ANTHROPIC_EFFORT",
        "ANTHROPIC_REFUSAL_FALLBACK",
        "LLM_PROVIDER",
        "AWS_DEFAULT_REGION",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "KEYCLOAK_ISSUER",
        "KEYCLOAK_AUDIENCE",
        "KEYCLOAK_INTERNAL_URL",
        "KEYCLOAK_CRON_CLIENT_SECRET",
        "SIM_MODE",
        "SIM_START_DATE",
        "SIM_CLOCK_FROM_DB",
        "MAX_AGENT_ITERATIONS",
        "QUESTIONS_PER_DAY",
        "LOG_LEVEL",
        "RATE_LIMIT_CHAT_PER_MINUTE",
        "RATE_LIMIT_CHAT_PER_DAY",
        "RATE_LIMIT_SIM_PER_MINUTE",
        "RATE_LIMIT_WS_CONNECT_PER_MINUTE",
        "API_DOCS_ENABLED",
    }
)
OPTIONAL_FIELDS = (
    "ANTHROPIC_API_KEY",
    "AWS_DEFAULT_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "KEYCLOAK_ISSUER",
    "KEYCLOAK_AUDIENCE",
    "KEYCLOAK_INTERNAL_URL",
    "KEYCLOAK_CRON_CLIENT_SECRET",
)


def _from_env(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    return Settings(_env_file=None)


def _env_example_keys() -> list[str]:
    """Every variable python-dotenv reads from .env.example (also `export X=…`, `X = …`)."""
    with ENV_EXAMPLE.open(encoding="utf-8") as stream:
        bindings = list(parse_stream(stream))
    assert not [b.original.string for b in bindings if b.error], "unparsable lines"
    return [b.key for b in bindings if b.key is not None]


def _compose_service(compose: str, service: str) -> tuple[dict[str, str], list[str]]:
    """(environment, ports) of one service, read by indentation: no YAML library needed."""

    def indent(line: str) -> int:
        return len(line) - len(line.lstrip())

    def children(lines: list[str], header: str) -> list[str]:
        start = next(i for i, line in enumerate(lines) if line.strip() == header)
        block = []
        for line in lines[start + 1 :]:
            if line.strip() and not line.lstrip().startswith("#"):
                if indent(line) <= indent(lines[start]):
                    break
                block.append(line)
        return block

    body = children(children(compose.splitlines(), "services:"), f"{service}:")
    environment = {}
    for line in children(body, "environment:"):
        item = line.strip().removeprefix("- ")
        name, _, value = item.partition("=" if "=" in item.split(":")[0] else ":")
        environment[name.strip()] = value.strip().strip("\"'")
    ports = [line.strip().removeprefix("- ").strip("\"'") for line in children(body, "ports:")]
    return environment, ports


# ── defaults and sources ─────────────────────────────────────────────────────────────────────


def test_settings_fields_are_exactly_the_documented_variables() -> None:
    # TZ is deliberately not a setting: day boundaries are always Europe/Bucharest (app.clock).
    assert set(Settings.model_fields) == FIELDS


def test_settings_defaults_match_the_documented_values(settings: Settings) -> None:
    # SecretStr compares by its secret value, so the whole model is checked in one go.
    assert settings.model_dump() == {
        "DATABASE_URL": SecretStr(
            "postgresql+psycopg://cashguard:cashguard@localhost:5434/cashguard"
        ),
        "TEST_DATABASE_URL": SecretStr(
            "postgresql+psycopg://cashguard:cashguard@localhost:5435/cashguard_test"
        ),
        "ANTHROPIC_API_KEY": None,
        "ANTHROPIC_MODEL": "claude-sonnet-5-5",
        "ANTHROPIC_EFFORT": "low",
        "ANTHROPIC_REFUSAL_FALLBACK": False,
        "LLM_PROVIDER": "anthropic",
        "AWS_DEFAULT_REGION": None,
        "AWS_BEARER_TOKEN_BEDROCK": None,
        "AWS_ACCESS_KEY_ID": None,
        "AWS_SECRET_ACCESS_KEY": None,
        "AWS_SESSION_TOKEN": None,
        "KEYCLOAK_ISSUER": None,
        "KEYCLOAK_AUDIENCE": None,
        "KEYCLOAK_INTERNAL_URL": None,
        "KEYCLOAK_CRON_CLIENT_SECRET": None,
        "SIM_MODE": False,
        "SIM_START_DATE": date(2026, 6, 15),
        "SIM_CLOCK_FROM_DB": True,
        "MAX_AGENT_ITERATIONS": 6,
        "QUESTIONS_PER_DAY": 1,
        "LOG_LEVEL": "INFO",
        "RATE_LIMIT_CHAT_PER_MINUTE": 10,
        "RATE_LIMIT_CHAT_PER_DAY": 200,
        "RATE_LIMIT_SIM_PER_MINUTE": 5,
        "RATE_LIMIT_WS_CONNECT_PER_MINUTE": 10,
        "API_DOCS_ENABLED": False,
    }


def test_test_database_url_matches_the_compose_db_test_service(settings: Settings) -> None:
    # HANDOFFS H-1: the compose service and this default must change together.
    url = settings.TEST_DATABASE_URL.get_secret_value()
    match = re.fullmatch(r"postgresql\+psycopg://(\w+):(\w+)@localhost:(\d+)/(\w+)", url)
    assert match is not None
    user, password, port, database = match.groups()
    environment, ports = _compose_service(
        (BACKEND_DIR / "docker-compose.yml").read_text(encoding="utf-8"), "db-test"
    )

    assert environment["POSTGRES_USER"] == user
    assert environment["POSTGRES_PASSWORD"] == password
    assert environment["POSTGRES_DB"] == database
    assert f"{port}:5432" in ports


def test_the_compose_reader_looks_inside_the_named_service_only() -> None:
    # A decoy service holding the expected values must not satisfy the db-test check.
    compose = """services:
  db:
    environment:
      POSTGRES_USER: cashguard_test
    ports:
      - "5433:5432"
  db-test:
    image: postgres:16
    environment:
      - POSTGRES_USER=other
    ports:
      - "5434:5432"
"""

    assert _compose_service(compose, "db-test") == ({"POSTGRES_USER": "other"}, ["5434:5432"])
    assert _compose_service(compose, "db") == ({"POSTGRES_USER": "cashguard_test"}, ["5433:5432"])


def test_settings_read_every_field_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _from_env(
        monkeypatch,
        DATABASE_URL="postgresql+psycopg://u:p@db:5432/app",
        TEST_DATABASE_URL="postgresql+psycopg://t:t@db-test:5432/test",
        ANTHROPIC_API_KEY=f"{KEY_PREFIX}from-env",
        ANTHROPIC_MODEL="claude-opus-5-5",
        ANTHROPIC_EFFORT="medium",
        ANTHROPIC_REFUSAL_FALLBACK="true",
        LLM_PROVIDER="BEDROCK",
        AWS_DEFAULT_REGION="us-west-2",
        AWS_BEARER_TOKEN_BEDROCK="bedrock-api-key",
        AWS_ACCESS_KEY_ID="AKIDEXAMPLE",
        AWS_SECRET_ACCESS_KEY="aws-secret",
        AWS_SESSION_TOKEN="aws-token",
        KEYCLOAK_ISSUER="https://auth.example.com/realms/cashguard",
        KEYCLOAK_AUDIENCE="savings-api",
        KEYCLOAK_INTERNAL_URL="http://keycloak:8080/realms/cashguard",
        SIM_CLOCK_FROM_DB="false",
        KEYCLOAK_CRON_CLIENT_SECRET="cron-secret",
        SIM_MODE="true",
        SIM_START_DATE="2026-07-01",
        MAX_AGENT_ITERATIONS="8",
        QUESTIONS_PER_DAY="2",
        LOG_LEVEL="DEBUG",
        RATE_LIMIT_CHAT_PER_MINUTE="11",
        RATE_LIMIT_CHAT_PER_DAY="201",
        RATE_LIMIT_SIM_PER_MINUTE="6",
        RATE_LIMIT_WS_CONNECT_PER_MINUTE="12",
        API_DOCS_ENABLED="true",
    )

    assert settings.model_dump() == {
        "DATABASE_URL": SecretStr("postgresql+psycopg://u:p@db:5432/app"),
        "TEST_DATABASE_URL": SecretStr("postgresql+psycopg://t:t@db-test:5432/test"),
        "ANTHROPIC_API_KEY": SecretStr(f"{KEY_PREFIX}from-env"),
        "ANTHROPIC_MODEL": "claude-opus-5-5",
        "ANTHROPIC_EFFORT": "medium",
        "ANTHROPIC_REFUSAL_FALLBACK": True,
        "LLM_PROVIDER": "bedrock",
        "AWS_DEFAULT_REGION": "us-west-2",
        "AWS_BEARER_TOKEN_BEDROCK": SecretStr("bedrock-api-key"),
        "AWS_ACCESS_KEY_ID": SecretStr("AKIDEXAMPLE"),
        "AWS_SECRET_ACCESS_KEY": SecretStr("aws-secret"),
        "AWS_SESSION_TOKEN": SecretStr("aws-token"),
        "KEYCLOAK_ISSUER": "https://auth.example.com/realms/cashguard",
        "KEYCLOAK_AUDIENCE": "savings-api",
        "KEYCLOAK_INTERNAL_URL": "http://keycloak:8080/realms/cashguard",
        "SIM_CLOCK_FROM_DB": False,
        "KEYCLOAK_CRON_CLIENT_SECRET": SecretStr("cron-secret"),
        "SIM_MODE": True,
        "SIM_START_DATE": date(2026, 7, 1),
        "MAX_AGENT_ITERATIONS": 8,
        "QUESTIONS_PER_DAY": 2,
        "LOG_LEVEL": "DEBUG",
        "RATE_LIMIT_CHAT_PER_MINUTE": 11,
        "RATE_LIMIT_CHAT_PER_DAY": 201,
        "RATE_LIMIT_SIM_PER_MINUTE": 6,
        "RATE_LIMIT_WS_CONNECT_PER_MINUTE": 12,
        "API_DOCS_ENABLED": True,
    }


def test_settings_read_a_dotenv_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SIM_MODE=true\nMAX_AGENT_ITERATIONS=9\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.SIM_MODE is True
    assert settings.MAX_AGENT_ITERATIONS == 9


def test_environment_beats_the_dotenv_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # A .env copied into the container must not override what compose / the host sets.
    env_file = tmp_path / ".env"
    env_file.write_text("SIM_MODE=false\nLOG_LEVEL=ERROR\n", encoding="utf-8")
    monkeypatch.setenv("SIM_MODE", "true")

    settings = Settings(_env_file=env_file)

    assert settings.SIM_MODE is True
    assert settings.LOG_LEVEL == "ERROR"


def test_a_missing_dotenv_file_gives_the_defaults(tmp_path: Path) -> None:
    settings = Settings(_env_file=tmp_path / "does-not-exist.env")

    assert settings.MAX_AGENT_ITERATIONS == 6


def test_a_malformed_dotenv_line_does_not_stop_the_others(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SIM_MODE=true\nthis line is not a variable\nQUESTIONS_PER_DAY=3\n")

    settings = Settings(_env_file=env_file)

    assert settings.SIM_MODE is True
    assert settings.QUESTIONS_PER_DAY == 3


def test_dotenv_is_read_as_utf8(tmp_path: Path) -> None:
    # In a LANG=C container the locale encoding is ASCII; the file must still parse.
    env_file = tmp_path / ".env"
    env_file.write_bytes("# notă: ăîșț ĂÎȘȚ\nKEYCLOAK_AUDIENCE=cont-ăîșț\n".encode())

    settings = Settings(_env_file=env_file)

    assert settings.KEYCLOAK_AUDIENCE == "cont-ăîșț"


def test_unknown_variables_are_ignored(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # Compose-only variables (POSTGRES_*, KC_*) live in the same .env.
    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=x\nKC_HOSTNAME=https://auth.example.com\n")
    monkeypatch.setenv("SOMETHING_ELSE", "1")

    settings = Settings(_env_file=env_file)

    assert settings.SIM_MODE is False


# ── validation ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("true", True), ("1", True), ("TRUE", True), ("false", False), ("0", False)],
)
def test_sim_mode_accepts_boolean_spellings(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    assert _from_env(monkeypatch, SIM_MODE=raw).SIM_MODE is expected


def test_sim_mode_rejects_a_non_boolean(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="SIM_MODE"):
        _from_env(monkeypatch, SIM_MODE="maybe")


def test_sim_start_date_accepts_a_leap_day(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _from_env(monkeypatch, SIM_START_DATE="2028-02-29").SIM_START_DATE == date(2028, 2, 29)


@pytest.mark.parametrize(
    "raw",
    [
        "2026-02-30",  # no such day
        "2027-02-29",  # not a leap year
        "15.06.2026",  # Romanian notation
        "2026-6-15",  # not zero-padded
        "20260615",  # digits only
        "1781481600",  # pydantic would read a Unix timestamp as 2026-06-15
        "2026-06-15T00:00:00",  # a datetime, not a date
    ],
)
def test_sim_start_date_accepts_only_iso_dates(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    with pytest.raises(ValidationError, match="SIM_START_DATE"):
        _from_env(monkeypatch, SIM_START_DATE=raw)


def test_sim_start_date_may_have_surrounding_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _from_env(monkeypatch, SIM_START_DATE=" 2026-06-15 ").SIM_START_DATE == date(2026, 6, 15)


def test_sim_start_date_in_code_must_be_a_date() -> None:
    assert Settings(SIM_START_DATE=date(2026, 6, 15)).SIM_START_DATE == date(2026, 6, 15)
    for value in (1781481600, datetime(2026, 6, 15, tzinfo=UTC)):  # a timestamp; a datetime
        with pytest.raises(ValidationError, match="SIM_START_DATE"):
            Settings(SIM_START_DATE=value)  # type: ignore[arg-type]


@pytest.mark.parametrize(("raw", "expected"), [("1", 1), ("6", 6), ("20", 20)])
def test_max_agent_iterations_accepts_1_to_20(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
) -> None:
    assert _from_env(monkeypatch, MAX_AGENT_ITERATIONS=raw).MAX_AGENT_ITERATIONS == expected


@pytest.mark.parametrize("raw", ["0", "21", "-1", "six"])
def test_max_agent_iterations_rejects_anything_else(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    with pytest.raises(ValidationError, match="MAX_AGENT_ITERATIONS"):
        _from_env(monkeypatch, MAX_AGENT_ITERATIONS=raw)


@pytest.mark.parametrize(("raw", "expected"), [("1", 1), ("10", 10)])
def test_questions_per_day_accepts_1_to_10(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: int
) -> None:
    assert _from_env(monkeypatch, QUESTIONS_PER_DAY=raw).QUESTIONS_PER_DAY == expected


@pytest.mark.parametrize("raw", ["0", "11"])
def test_questions_per_day_rejects_anything_else(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    with pytest.raises(ValidationError, match="QUESTIONS_PER_DAY"):
        _from_env(monkeypatch, QUESTIONS_PER_DAY=raw)


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_anthropic_effort_accepts_every_level_of_the_model(
    monkeypatch: pytest.MonkeyPatch, effort: str
) -> None:
    assert _from_env(monkeypatch, ANTHROPIC_EFFORT=effort).ANTHROPIC_EFFORT == effort


def test_anthropic_effort_is_case_and_space_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _from_env(monkeypatch, ANTHROPIC_EFFORT=" LOW ").ANTHROPIC_EFFORT == "low"


@pytest.mark.parametrize("raw", ["lw", "minimal", "disabled"])
def test_anthropic_effort_rejects_unknown_levels(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    # A typo fails at startup instead of turning every Claude request into a 400.
    with pytest.raises(ValidationError, match="ANTHROPIC_EFFORT"):
        _from_env(monkeypatch, ANTHROPIC_EFFORT=raw)


def test_anthropic_model_rejects_blank_and_strips_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _from_env(monkeypatch, ANTHROPIC_MODEL=" claude-sonnet-5-5 ").ANTHROPIC_MODEL == (
        "claude-sonnet-5-5"
    )
    with pytest.raises(ValidationError, match="ANTHROPIC_MODEL"):
        _from_env(monkeypatch, ANTHROPIC_MODEL="   ")


def test_log_level_is_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _from_env(monkeypatch, LOG_LEVEL=" debug ").LOG_LEVEL == "DEBUG"


def test_log_level_rejects_unknown_levels(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValidationError, match="LOG_LEVEL"):
        _from_env(monkeypatch, LOG_LEVEL="verbose")


@pytest.mark.parametrize("field", OPTIONAL_FIELDS)
@pytest.mark.parametrize("raw", ["", "   "])
def test_blank_optional_values_mean_not_set(
    monkeypatch: pytest.MonkeyPatch, field: str, raw: str
) -> None:
    # .env.example ships `ANTHROPIC_API_KEY=`: a blank key must not look like a key.
    assert getattr(_from_env(monkeypatch, **{field: raw}), field) is None


def test_empty_values_mean_not_set_for_every_field(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, settings: Settings
) -> None:
    # `SIM_MODE=` or `LOG_LEVEL=` in a .env falls back to the default instead of failing.
    env_file = tmp_path / ".env"
    env_file.write_text("".join(f"{name}=\n" for name in FIELDS))
    monkeypatch.setenv("MAX_AGENT_ITERATIONS", "")

    assert Settings(_env_file=env_file) == settings


def test_blank_optional_values_passed_in_code_mean_not_set() -> None:
    settings = Settings(_env_file=None, ANTHROPIC_API_KEY=SecretStr("  "), KEYCLOAK_AUDIENCE="")

    assert settings.ANTHROPIC_API_KEY is None
    assert settings.KEYCLOAK_AUDIENCE is None


def test_optional_values_are_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _from_env(monkeypatch, ANTHROPIC_API_KEY=f" {KEY_PREFIX}padded \n")

    assert settings.ANTHROPIC_API_KEY is not None
    assert settings.ANTHROPIC_API_KEY.get_secret_value() == f"{KEY_PREFIX}padded"


def test_keycloak_issuer_drops_a_trailing_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    # The token's `iss` is compared exactly (arch 5.1), and Keycloak never adds a slash.
    settings = _from_env(monkeypatch, KEYCLOAK_ISSUER="http://localhost:8080/realms/cashguard/")

    assert settings.KEYCLOAK_ISSUER == "http://localhost:8080/realms/cashguard"


@pytest.mark.parametrize(
    "raw",
    [
        "localhost:8080/realms/cashguard",  # no scheme
        "ftp://auth.example.com/realms/x",
        "https://",
        "http://localhost:8080",  # no realm
        "http://localhost:8080/",
        "http://localhost:8080/realms/",
        "http://localhost:8080/cashguard",
        "http://localhost:abc/realms/cashguard",  # bad port
        "http://localhost:8080/realms/cashguard?x=1",
        "http://localhost:8080/realms/cashguard#f",
    ],
)
def test_keycloak_issuer_must_be_a_realm_url(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    # Anything else gives a 401 on every request at demo time (arch 5.1).
    with pytest.raises(ValidationError, match="KEYCLOAK_ISSUER"):
        _from_env(monkeypatch, KEYCLOAK_ISSUER=raw)


@pytest.mark.parametrize(
    "raw",
    [
        "https://auth.example.com/realms/cashguard",
        "http://localhost:8080/auth/realms/cashguard",  # older Keycloak path prefix
    ],
)
def test_keycloak_issuer_accepts_realm_urls(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    assert _from_env(monkeypatch, KEYCLOAK_ISSUER=raw).KEYCLOAK_ISSUER == raw


@pytest.mark.parametrize("field", ["DATABASE_URL", "TEST_DATABASE_URL"])
@pytest.mark.parametrize(
    "raw",
    [
        "   ",
        "not a url",
        "postgresql://u:p@db:5432/app",  # psycopg2, which isn't installed
        "postgresql+asyncpg://u:p@db:5432/app",
        "postgresql+psycopg://",  # no host
        "postgresql+psycopg://u:p@db:5432/",  # no database
        "postgresql+psycopg://u:p@db:abc/app",  # bad port
    ],
)
def test_database_urls_must_be_psycopg_urls(
    monkeypatch: pytest.MonkeyPatch, field: str, raw: str
) -> None:
    # Caught at startup, not at the first query.
    with pytest.raises(ValidationError, match=field):
        _from_env(monkeypatch, **{field: raw})


def test_a_database_url_that_is_not_text_is_rejected() -> None:
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        Settings(DATABASE_URL=5432)  # type: ignore[arg-type]


def test_database_url_is_stripped(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _from_env(monkeypatch, DATABASE_URL=" postgresql+psycopg://u:p@db:5432/app ")

    assert settings.DATABASE_URL.get_secret_value() == "postgresql+psycopg://u:p@db:5432/app"


def test_a_rejected_database_url_does_not_leak_its_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # pydantic quotes the input in its error text by default; the error is logged at startup.
    with pytest.raises(ValidationError) as error:
        _from_env(monkeypatch, DATABASE_URL="postgresql://app:pw-in-error-789@db:5432/app")

    assert "pw-in-error-789" not in str(error.value)
    assert "DATABASE_URL" in str(error.value)


def test_every_value_may_have_surrounding_spaces(monkeypatch: pytest.MonkeyPatch) -> None:
    # One rule for every field (a pasted value, or `NAME = value` in a .env).
    values = {
        "DATABASE_URL": "postgresql+psycopg://u:p@db:5432/app",
        "TEST_DATABASE_URL": "postgresql+psycopg://t:t@db-test:5432/test",
        "ANTHROPIC_API_KEY": f"{KEY_PREFIX}spaced",
        "ANTHROPIC_MODEL": "claude-opus-5-5",
        "ANTHROPIC_EFFORT": "high",
        "ANTHROPIC_REFUSAL_FALLBACK": "true",
        "LLM_PROVIDER": "bedrock",
        "AWS_DEFAULT_REGION": "us-west-2",
        "AWS_BEARER_TOKEN_BEDROCK": "bedrock-api-key",
        "AWS_ACCESS_KEY_ID": "AKIDEXAMPLE",
        "AWS_SECRET_ACCESS_KEY": "aws-secret",
        "AWS_SESSION_TOKEN": "aws-token",
        "KEYCLOAK_ISSUER": "https://auth.example.com/realms/cashguard",
        "KEYCLOAK_AUDIENCE": "savings-api",
        "KEYCLOAK_INTERNAL_URL": "http://keycloak:8080/realms/cashguard",
        "SIM_CLOCK_FROM_DB": "false",
        "KEYCLOAK_CRON_CLIENT_SECRET": "cron-secret",
        "SIM_MODE": "true",
        "SIM_START_DATE": "2026-07-01",
        "MAX_AGENT_ITERATIONS": "8",
        "QUESTIONS_PER_DAY": "2",
        "LOG_LEVEL": "WARNING",
        "RATE_LIMIT_CHAT_PER_MINUTE": "3",
        "RATE_LIMIT_CHAT_PER_DAY": "30",
        "RATE_LIMIT_SIM_PER_MINUTE": "2",
        "RATE_LIMIT_WS_CONNECT_PER_MINUTE": "4",
        "API_DOCS_ENABLED": "true",
    }
    assert set(values) == FIELDS
    plain = _from_env(monkeypatch, **values)

    padded = _from_env(monkeypatch, **{name: f"  {value} \t" for name, value in values.items()})

    assert padded == plain


# ── secrets ──────────────────────────────────────────────────────────────────────────────────

SECRETS = {
    "DATABASE_URL": "postgresql+psycopg://app:db-pass-123@db:5432/app",
    "TEST_DATABASE_URL": "postgresql+psycopg://ci:ci-pass-456@db-test:5432/test",
    "ANTHROPIC_API_KEY": f"{KEY_PREFIX}api03-real-looking-key",
    "KEYCLOAK_CRON_CLIENT_SECRET": "cron-client-secret-789",
    "AWS_BEARER_TOKEN_BEDROCK": "bedrock-api-key-987",
    "AWS_SECRET_ACCESS_KEY": "aws-secret-access-key-321",
    "AWS_SESSION_TOKEN": "aws-session-token-654",
}


def test_secrets_never_appear_in_repr_str_or_dumps(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _from_env(monkeypatch, **SECRETS)
    renderings = {
        "repr": repr(settings),
        "str": str(settings),
        "model_dump": str(settings.model_dump()),
        "model_dump_json": settings.model_dump_json(),
        "model_dump(json)": str(settings.model_dump(mode="json")),
    }

    for name, text in renderings.items():
        for field, secret in SECRETS.items():
            assert secret not in text, f"{field} leaks through {name}"
            assert "db-pass-123" not in text
            assert "ci-pass-456" not in text


def test_secrets_are_still_readable_on_purpose(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _from_env(monkeypatch, **SECRETS)

    for field, secret in SECRETS.items():
        value = getattr(settings, field)
        assert isinstance(value, SecretStr)
        assert value.get_secret_value() == secret


@given(suffix=st.text(alphabet=string.ascii_letters + string.digits + "-_", min_size=8))
def test_any_api_key_stays_masked(suffix: str) -> None:
    key = f"{KEY_PREFIX}{suffix}"
    settings = Settings(_env_file=None, ANTHROPIC_API_KEY=SecretStr(key))

    assert key not in repr(settings)
    assert key not in settings.model_dump_json()


def test_settings_are_frozen(settings: Settings) -> None:
    with pytest.raises(ValidationError, match="frozen"):
        settings.SIM_MODE = True  # type: ignore[misc]


# ── .env.example ─────────────────────────────────────────────────────────────────────────────


def test_env_example_lists_exactly_the_settings() -> None:
    keys = _env_example_keys()

    assert len(keys) == len(set(keys)), "a variable is listed twice"
    assert set(keys) - NON_APP_KEYS == set(Settings.model_fields)
    assert set(keys) >= NON_APP_KEYS
    assert not NON_APP_KEYS & set(Settings.model_fields)


def test_env_example_holds_no_key() -> None:
    assert KEY_PREFIX not in ENV_EXAMPLE.read_text(encoding="utf-8")


def test_env_example_is_itself_valid() -> None:
    settings = Settings(_env_file=ENV_EXAMPLE)

    assert settings.ANTHROPIC_API_KEY is None
    assert settings.KEYCLOAK_CRON_CLIENT_SECRET is None
    assert settings.SIM_MODE is True
    assert settings.ANTHROPIC_REFUSAL_FALLBACK is False
    assert settings.KEYCLOAK_ISSUER == "http://localhost:8081/realms/cashguard"  # B1's port


# ── get_settings ────────────────────────────────────────────────────────


def test_get_settings_is_cached_until_cleared(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SIM_MODE=true\n")
    monkeypatch.setitem(Settings.model_config, "env_file", env_file)

    first = get_settings()

    assert first.SIM_MODE is True
    assert get_settings() is first
    get_settings.cache_clear()
    assert get_settings() is not first
