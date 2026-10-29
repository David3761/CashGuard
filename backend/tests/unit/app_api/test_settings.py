"""The app API's settings: defaults (off in code), validation, and .env.example turning it on."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import BACKEND_DIR, Settings


def test_defaults():
    s = Settings(_env_file=None)
    assert s.APP_API_ENABLED is False
    assert s.APP_API_USER == "a0000000-0000-4000-8000-000000000001"  # Matei (realm + seed)
    assert s.APP_API_MAX_TEXT_CHARS == 2000
    assert s.APP_API_REPLY_TIMEOUT_S == 120
    assert s.APP_API_HISTORY_LIMIT == 100
    assert s.APP_API_MAX_DEVICES == 5
    assert s.FCM_SERVICE_ACCOUNT_FILE is None
    assert s.FCM_PROJECT_ID is None


def test_env_example_turns_the_app_api_on():
    s = Settings(_env_file=BACKEND_DIR / ".env.example")
    assert s.APP_API_ENABLED is True
    assert s.APP_API_CORS_ORIGIN_REGEX == r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    assert s.FCM_SERVICE_ACCOUNT_FILE is None  # blank = not set


def test_blank_values_mean_the_default(monkeypatch: pytest.MonkeyPatch):
    for name in ("APP_API_CORS_ORIGIN_REGEX", "FCM_SERVICE_ACCOUNT_FILE", "FCM_PROJECT_ID"):
        monkeypatch.setenv(name, "")
    s = Settings(_env_file=None)
    assert s.APP_API_CORS_ORIGIN_REGEX == r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    assert s.FCM_SERVICE_ACCOUNT_FILE is None
    assert s.FCM_PROJECT_ID is None


def test_fcm_file_is_a_path(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FCM_SERVICE_ACCOUNT_FILE", "/run/secrets/firebase.json")
    assert Settings(_env_file=None).FCM_SERVICE_ACCOUNT_FILE == Path("/run/secrets/firebase.json")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("APP_API_MAX_TEXT_CHARS", "0"),
        ("APP_API_REPLY_TIMEOUT_S", "0"),
        ("APP_API_MAX_DEVICES", "0"),
        ("APP_API_CORS_ORIGIN_REGEX", "(unclosed"),
        ("APP_API_USER", " "),
        ("APP_API_ENABLED", "maybe"),
    ],
)
def test_bad_values_are_rejected(monkeypatch: pytest.MonkeyPatch, name: str, value: str):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
