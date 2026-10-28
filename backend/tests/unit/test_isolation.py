"""Every test is isolated from the developer's setup, except `live` tests: the app's settings
(F1.2 review #1) and every `ANTHROPIC_*` variable, which the anthropic SDK reads by itself
(F1.2-fix: a redirected base URL, extra headers, body logging, another credential).

A developer's shell variables and real backend/.env exist *before* any test fixture runs. The
module-scoped fixture below recreates that (higher-scoped fixtures are set up first), and an inner
pytest session (pytester) checks the real conftest end to end, including the `live` opt-out.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import anthropic
import pytest

from app.config import BACKEND_DIR, ENV_FILE, Settings, get_settings
from app.main import create_app

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
# What a developer shell (Claude Code sets some of these) may hold for the SDK.
SDK_VARIABLES = {
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:9/redirected",
    "ANTHROPIC_CUSTOM_HEADERS": "X-Leak: 1",
    "ANTHROPIC_LOG": "debug",
    "ANTHROPIC_AUTH_TOKEN": "a-real-token",
}


def _anthropic_variables() -> list[str]:
    return sorted(name for name in os.environ if name.upper().startswith("ANTHROPIC_"))


@pytest.fixture(scope="module")
def developer_setup(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A developer's real .env and shell variables, in place before each test's isolation."""
    env_file = tmp_path_factory.mktemp("developer") / ".env"
    env_file.write_text("MAX_AGENT_ITERATIONS=20\nANTHROPIC_API_KEY=a-real-key\n")
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(Settings.model_config, "env_file", env_file)
        patch.setenv("SIM_MODE", "true")
        patch.setenv("log_level", "DEBUG")  # pydantic-settings matches names in any case
        for name, value in SDK_VARIABLES.items():
            patch.setenv(name, value)
        yield


@pytest.mark.usefixtures("developer_setup")
def test_settings_ignore_the_developer_setup() -> None:
    for settings in (Settings(), get_settings(), create_app().state.settings):
        assert settings.SIM_MODE is False
        assert settings.MAX_AGENT_ITERATIONS == 6
        assert settings.LOG_LEVEL == "INFO"
        assert settings.ANTHROPIC_API_KEY is None


@pytest.mark.usefixtures("developer_setup")
def test_the_anthropic_sdk_sees_none_of_the_developer_variables() -> None:
    assert _anthropic_variables() == []
    assert str(anthropic.Anthropic(api_key="test-key").base_url) == "https://api.anthropic.com"


@pytest.mark.usefixtures("developer_setup")
def test_a_test_can_still_set_its_own_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_MODE", "true")

    assert Settings().SIM_MODE is True


INNER_TESTS = """
import os
import pytest
from app.config import ENV_FILE, Settings, get_settings


def test_normal_test_is_isolated():
    assert Settings.model_config["env_file"] is None
    assert Settings().SIM_MODE is False
    assert get_settings().ANTHROPIC_API_KEY is None
    assert not [name for name in os.environ if name.upper().startswith("ANTHROPIC_")]


@pytest.mark.live
def test_live_test_sees_the_real_setup():
    assert Settings.model_config["env_file"] == ENV_FILE
    assert Settings().SIM_MODE is True
    key = Settings().ANTHROPIC_API_KEY
    assert key is not None and key.get_secret_value() == "live-key-from-the-shell"
    assert os.environ["ANTHROPIC_BASE_URL"] == "http://127.0.0.1:9/live"
"""


@pytest.mark.slow
def test_live_tests_opt_out_of_the_isolation(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The inner session inherits this environment, as it would inherit a developer's shell.
    monkeypatch.setenv("SIM_MODE", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "live-key-from-the-shell")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:9/live")
    monkeypatch.setenv("PYTHONPATH", str(BACKEND_DIR))
    pytester.makeconftest(CONFTEST.read_text(encoding="utf-8"))
    pytester.makeini("[pytest]\nmarkers =\n    live: real Claude\n    slow: slow\n")
    pytester.makepyfile(test_inner=INNER_TESTS)

    result = pytester.runpytest_subprocess("-m", "", "-p", "no:cacheprovider")

    result.assert_outcomes(passed=2)


def test_the_real_env_file_is_next_to_the_app() -> None:
    # The isolation swaps env_file for None during tests; the real value is checked in the
    # inner `live` test above. Here: the constant itself.
    assert BACKEND_DIR / ".env" == ENV_FILE
