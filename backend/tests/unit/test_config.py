import logging
from datetime import date

import pytest

from app.config import Settings


def test_settings_reads_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    monkeypatch.setenv("SIM_START_DATE", "2026-07-01")
    s = Settings(_env_file=None)
    assert s.ANTHROPIC_MODEL == "claude-test"
    assert date(2026, 7, 1) == s.SIM_START_DATE


def test_settings_reads_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.delenv("KEYCLOAK_ISSUER", raising=False)
    env = tmp_path / ".env"
    env.write_text("KEYCLOAK_ISSUER=https://auth.example.ro/realms/cashguard\n", encoding="utf-8")
    s = Settings(_env_file=env)
    assert s.KEYCLOAK_ISSUER == "https://auth.example.ro/realms/cashguard"


@pytest.mark.parametrize(
    ("raw", "expected"), [("true", True), ("1", True), ("false", False), ("0", False)]
)
def test_settings_sim_mode_accepts_bool_spellings(monkeypatch, raw, expected):
    monkeypatch.setenv("SIM_MODE", raw)
    assert Settings(_env_file=None).SIM_MODE is expected


def test_settings_missing_optional_key_is_none(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert Settings(_env_file=None).ANTHROPIC_API_KEY is None


def test_settings_defaults_match_arch_doc(monkeypatch):
    for var in ("ANTHROPIC_MODEL", "ANTHROPIC_EFFORT", "SIM_START_DATE", "MAX_AGENT_ITERATIONS"):
        monkeypatch.delenv(var, raising=False)
    s = Settings(_env_file=None)
    assert s.ANTHROPIC_MODEL == "claude-sonnet-5-5"
    assert s.ANTHROPIC_EFFORT == "low"
    assert date(2026, 6, 15) == s.SIM_START_DATE
    assert s.MAX_AGENT_ITERATIONS == 6
    assert s.QUESTIONS_PER_DAY == 1


def test_settings_secret_never_appears_in_logged_dump(monkeypatch, caplog):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-super-secret")
    s = Settings(_env_file=None)
    with caplog.at_level(logging.INFO):
        logging.getLogger("test").info("settings: %s", s.model_dump())
        logging.getLogger("test").info("settings: %r", s)
    assert "sk-ant-super-secret" not in caplog.text
    assert s.ANTHROPIC_API_KEY is not None
    assert s.ANTHROPIC_API_KEY.get_secret_value() == "sk-ant-super-secret"
