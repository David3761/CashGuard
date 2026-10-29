"""Shared test config. bomboe's F3 adds the db / api / auth / ws fixtures here (HANDOFFS H-4)."""

import logging
import os
from collections.abc import Iterator
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
pytest_plugins = ["pytester"]


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
    get_settings.cache_clear()
    # A fresh real clock, not "whatever is installed": a clock installed at import/collection
    # time (a module-level set_clock, or an app built in SIM_MODE) must not leak into tests.
    real_clock = clock.RealClock()
    clock.set_clock(real_clock)
    assert clock.get_clock() is real_clock, "a use_clock() block was entered and never left"
    loggers = [logging.getLogger(name) for name in ("", "anthropic", "httpx", "httpx2", "httpcore")]
    saved = [(logger, logger.level, list(logger.handlers)) for logger in loggers]
    yield
    for logger, level, handlers in saved:
        logger.setLevel(level)
        logger.handlers[:] = handlers
    clock.set_clock(clock.RealClock())
    get_settings.cache_clear()


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
