"""docker-compose.yml structure (B1).

Uses `docker compose config`, which needs the docker CLI, not the daemon.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed")


@pytest.fixture(scope="module")
def compose() -> dict:
    out = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(out.stdout)


def published(service: dict) -> set[tuple[str, int]]:
    return {(str(p["published"]), p["target"]) for p in service.get("ports", [])}


def test_compose_config_is_valid_and_has_core_services(compose):
    assert {"db", "db-test", "api"} <= set(compose["services"])


def test_compose_databases_are_postgres_16(compose):
    for name in ("db", "db-test"):
        assert compose["services"][name]["image"].startswith("postgres:16")


def test_compose_db_keeps_data_in_a_named_volume(compose):
    mounts = compose["services"]["db"]["volumes"]
    assert any(m["type"] == "volume" and m["target"] == "/var/lib/postgresql/data" for m in mounts)


def test_compose_db_test_is_on_5433_and_in_tmpfs(compose):
    svc = compose["services"]["db-test"]
    assert ("5433", 5432) in published(svc)
    assert any(t.startswith("/var/lib/postgresql/data") for t in svc["tmpfs"])


def test_compose_dev_db_avoids_host_port_5432(compose):
    assert ("5432", 5432) not in published(compose["services"]["db"])


def test_compose_databases_have_healthchecks(compose):
    for name in ("db", "db-test"):
        assert "pg_isready" in " ".join(compose["services"][name]["healthcheck"]["test"])


def test_compose_api_runs_exactly_one_uvicorn_worker(compose):
    # The WebSocket manager is in memory (arch 5.2): more workers would split the sockets.
    command = compose["services"]["api"]["command"]
    assert "uvicorn" in command
    assert command[command.index("--workers") + 1] == "1"


def test_compose_api_waits_for_a_healthy_db(compose):
    assert compose["services"]["api"]["depends_on"]["db"]["condition"] == "service_healthy"


def test_compose_api_reaches_db_by_service_name(compose):
    env = compose["services"]["api"]["environment"]
    assert "@db:5432/" in env["DATABASE_URL"]
