"""F1.2 review #1: every test is isolated from the developer's settings, except `live` tests.

A developer's shell variables and real backend/.env exist *before* any test fixture runs. The
module-scoped fixture below recreates that (higher-scoped fixtures are set up first), and an inner
pytest session (pytester) checks the real conftest end to end, including the `live` opt-out.
"""

from collections.abc import Iterator
from pathlib import Path

import pytest

from app.config import BACKEND_DIR, ENV_FILE, Settings, get_settings
from app.main import create_app

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"


@pytest.fixture(scope="module")
def developer_setup(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A developer's real .env and shell variables, in place before each test's isolation."""
    env_file = tmp_path_factory.mktemp("developer") / ".env"
    env_file.write_text("MAX_AGENT_ITERATIONS=20\nANTHROPIC_API_KEY=a-real-key\n")
    with pytest.MonkeyPatch.context() as patch:
        patch.setitem(Settings.model_config, "env_file", env_file)
        patch.setenv("SIM_MODE", "true")
        patch.setenv("log_level", "DEBUG")  # pydantic-settings matches names in any case
        yield


@pytest.mark.usefixtures("developer_setup")
def test_settings_ignore_the_developer_setup() -> None:
    for settings in (Settings(), get_settings(), create_app().state.settings):
        assert settings.SIM_MODE is False
        assert settings.MAX_AGENT_ITERATIONS == 6
        assert settings.LOG_LEVEL == "INFO"
        assert settings.ANTHROPIC_API_KEY is None


@pytest.mark.usefixtures("developer_setup")
def test_a_test_can_still_set_its_own_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SIM_MODE", "true")

    assert Settings().SIM_MODE is True


INNER_TESTS = """
import pytest
from app.config import ENV_FILE, Settings, get_settings


def test_normal_test_is_isolated():
    assert Settings.model_config["env_file"] is None
    assert Settings().SIM_MODE is False
    assert get_settings().ANTHROPIC_API_KEY is None


@pytest.mark.live
def test_live_test_sees_the_real_setup():
    assert Settings.model_config["env_file"] == ENV_FILE
    assert Settings().SIM_MODE is True
    key = Settings().ANTHROPIC_API_KEY
    assert key is not None and key.get_secret_value() == "live-key-from-the-shell"
"""


@pytest.mark.slow
def test_live_tests_opt_out_of_the_isolation(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The inner session inherits this environment, as it would inherit a developer's shell.
    monkeypatch.setenv("SIM_MODE", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "live-key-from-the-shell")
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
