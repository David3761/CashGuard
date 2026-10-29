"""Shared test config: ours (F1.2 isolation, hypothesis, clock reset, make_client) merged with
bomboe's F3 (db / api / auth / ws fixtures, the folder → marker hook, the sim-date clock)."""

import logging
import os
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Protocol

import httpx
import pytest
from fastapi import FastAPI
from hypothesis import settings

from app import clock
from app.config import Settings, get_settings

# Determinism (how-we-work §7): the same examples on every run and machine, so a failure is
# reproducible. No deadline: parallel agents and CI load make timing-based failures flaky.
settings.register_profile("cashguard", derandomize=True, deadline=None, print_blob=True)
settings.load_profile("cashguard")

# `pytester` runs an inner pytest session (tests/unit/test_isolation.py checks the live opt-out).
pytest_plugins = [
    "pytester",
    "tests.fixtures.db",
    "tests.fixtures.auth",
    "tests.fixtures.api",
    "tests.fixtures.ws",
]

SIM_START = date(2026, 6, 15)
"""bomboe's test date: tests in tests/db, tests/api and tests/ws run at 2026-06-15 12:00."""

_MARKER_BY_FOLDER = {"db": pytest.mark.db, "api": pytest.mark.api, "ws": pytest.mark.ws}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """bomboe's hook: tests/db/* get the marker db, tests/api/* api, tests/ws/* ws."""
    for item in items:
        folder = Path(str(item.fspath)).parent.name
        if folder in _MARKER_BY_FOLDER:
            item.add_marker(_MARKER_BY_FOLDER[folder])


_PLATFORM_UNIT_FILES = frozenset(
    {"test_auth_tokens.py", "test_service_contracts.py", "test_ratelimit.py"}
)


def _platform_test(request: pytest.FixtureRequest) -> bool:
    """bomboe's db / api / ws tests (and his auth unit tests): they run at SIM_START with
    SIM_MODE on and his local Keycloak issuer (his defaults)."""
    path = Path(str(request.node.fspath))
    return path.parent.name in _MARKER_BY_FOLDER or path.name in _PLATFORM_UNIT_FILES


# ── Isolation (F1.2) ─────────────────────────────────────────────────────────────────────────
# Every test is isolated from the developer's real backend/.env and shell variables (a real
# ANTHROPIC_API_KEY there would make real, paid calls): Settings() and get_settings() see only
# the code defaults plus what the test itself sets. Every ANTHROPIC_* variable goes too: the
# anthropic SDK reads ANTHROPIC_BASE_URL, _CUSTOM_HEADERS, _LOG, _AUTH_TOKEN, … by itself (a
# developer shell, e.g. Claude Code, may set them). Tests marked `live` opt out, so they can use
# the real key and setup on purpose (`-m live`).


def _isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    fields = {name.lower() for name in Settings.model_fields}  # pydantic-settings ignores case
    for key in list(os.environ):
        if key.lower() in fields or key.upper().startswith("ANTHROPIC_"):
            monkeypatch.delenv(key)


@pytest.fixture(autouse=True)
def _restore_global_state(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Isolate the settings, and undo process-wide state a test may change: the cached
    settings, the installed clock (every test starts and ends with a real clock), and the
    logging setup (create_app configures it)."""
    if request.node.get_closest_marker("live") is None:
        _isolate_environment(monkeypatch)
    platform = _platform_test(request)
    if platform:
        # bomboe's environment: the simulator is on, but its clock isn't read from the DB at
        # app startup (his conftest's SIM_CLOCK_FROM_DB=false).
        monkeypatch.setenv("SIM_MODE", "true")
        monkeypatch.setenv("SIM_CLOCK_FROM_DB", "false")
        # his local Keycloak (B1/B5): the test tokens are issued for it
        monkeypatch.setenv("KEYCLOAK_ISSUER", "http://localhost:8081/realms/cashguard")
        monkeypatch.setenv("KEYCLOAK_AUDIENCE", "cashguard-api")
    get_settings.cache_clear()
    # One clock mechanism: a fresh clock per test, never "whatever is installed" (a clock
    # installed at import/collection time, or an app built in SIM_MODE, must not leak). Our
    # tests start with a real clock; bomboe's db/api/ws tests, and any test asking for
    # `fixed_clock`, start at SIM_START 12:00 Bucharest (his autouse `fixed_clock`).
    start: clock.Clock = (
        clock.FixedClock.on(SIM_START)
        if platform or "fixed_clock" in request.fixturenames
        else clock.RealClock()
    )
    clock.set_clock(start)
    assert clock.get_clock() is start, "a use_clock() block was entered and never left"
    loggers = [logging.getLogger(name) for name in ("", "anthropic", "httpx", "httpx2", "httpcore")]
    saved = [(logger, logger.level, list(logger.handlers)) for logger in loggers]
    yield
    for logger, level, handlers in saved:
        logger.setLevel(level)
        logger.handlers[:] = handlers
    clock.set_clock(clock.RealClock())
    get_settings.cache_clear()


@pytest.fixture
def fixed_clock() -> clock.FixedClock:
    """The test's FixedClock at SIM_START 12:00 (installed by `_restore_global_state`). A test
    that needs another time calls `clock.set_clock(FixedClock(...))`; it is undone after."""
    installed = clock.get_clock()
    assert isinstance(installed, clock.FixedClock)
    return installed


@pytest.fixture(name="settings")
def default_settings() -> Settings:
    """Settings with the code defaults only."""
    return Settings(_env_file=None)


# ── HTTP client ──────────────────────────────────────────────────────────────────────────────


class MakeClient(Protocol):
    def __call__(
        self, application: FastAPI, *, raise_app_exceptions: bool = True
    ) -> httpx.AsyncClient: ...


@pytest.fixture
def make_client() -> MakeClient:
    """Build an httpx client that calls the app in-process (no server, no network).

    `raise_app_exceptions=False` returns the 500 response instead of re-raising the app's error
    (Starlette re-raises after sending it).
    """

    def make(application: FastAPI, *, raise_app_exceptions: bool = True) -> httpx.AsyncClient:
        transport = httpx.ASGITransport(app=application, raise_app_exceptions=raise_app_exceptions)
        return httpx.AsyncClient(transport=transport, base_url="http://test")

    return make
