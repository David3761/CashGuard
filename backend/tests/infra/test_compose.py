"""docker-compose.yml structure (B1).

Uses `docker compose config`, which needs the docker CLI, not the daemon.
"""

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

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


def test_compose_db_test_is_on_5435_and_in_tmpfs(compose):
    # 5435, not the 5433 of the spec: 5432/5433 are often taken by other local Postgres projects.
    svc = compose["services"]["db-test"]
    assert ("5435", 5432) in published(svc)
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


def test_compose_keycloak_is_pinned_and_imports_the_realm(compose):
    kc = compose["services"]["keycloak"]
    image, _, tag = kc["image"].rpartition(":")
    assert image == "quay.io/keycloak/keycloak"
    assert tag and tag != "latest"
    assert "--import-realm" in kc["command"]
    mounts = kc["volumes"]
    assert any(
        m["source"].endswith("keycloak/realm-cashguard.json")
        and m["target"].startswith("/opt/keycloak/data/import/")
        for m in mounts
    )


def test_compose_keycloak_stores_its_data_in_postgres(compose):
    kc = compose["services"]["keycloak"]
    env = kc["environment"]
    assert env["KC_DB"] == "postgres"
    assert env["KC_DB_URL"] == "jdbc:postgresql://db:5432/keycloak"
    assert kc["depends_on"]["db"]["condition"] == "service_healthy"


def test_compose_db_creates_the_keycloak_database_on_first_start(compose):
    mounts = compose["services"]["db"]["volumes"]
    assert any(m["target"].startswith("/docker-entrypoint-initdb.d") for m in mounts)
    env = compose["services"]["db"]["environment"]
    assert env["KC_DB_PASSWORD"] == compose["services"]["keycloak"]["environment"]["KC_DB_PASSWORD"]


def test_compose_keycloak_issuer_host_is_fixed(compose):
    # Every token's `iss` must match the API's KEYCLOAK_ISSUER, whoever asked for it (D36).
    env = compose["services"]["keycloak"]["environment"]
    assert env["KC_HOSTNAME"]
    assert env["KC_HOSTNAME_BACKCHANNEL_DYNAMIC"] == "true"


def test_compose_keycloak_host_port_matches_its_public_hostname(compose):
    # A token fetched from the host must carry the same `iss` the API checks.
    kc = compose["services"]["keycloak"]
    host_port = urlparse(kc["environment"]["KC_HOSTNAME"]).port
    assert (str(host_port), 8080) in published(kc)
    issuer = compose["services"]["api"]["environment"]["KEYCLOAK_ISSUER"]
    assert issuer == kc["environment"]["KC_HOSTNAME"] + "/realms/cashguard"


def test_compose_cron_calls_the_api_with_the_cron_client(compose):
    cron = compose["services"]["cron"]
    env = cron["environment"]
    assert env["API_URL"] == "http://api:8000/api"
    assert env["KEYCLOAK_TOKEN_URL"] == (
        "http://keycloak:8080/realms/cashguard/protocol/openid-connect/token"
    )
    assert (
        env["CRON_CLIENT_SECRET"]
        == compose["services"]["keycloak"]["environment"]["KC_CRON_CLIENT_SECRET"]
    )
    assert env["TZ"] == "Europe/Bucharest"
    assert {"api", "keycloak"} <= set(cron["depends_on"])


def test_compose_api_fetches_keys_from_keycloak_inside_the_network(compose):
    env = compose["services"]["api"]["environment"]
    assert env["KEYCLOAK_INTERNAL_URL"].startswith("http://keycloak:8080/realms/cashguard")
    assert env["KEYCLOAK_ISSUER"].endswith("/realms/cashguard")
