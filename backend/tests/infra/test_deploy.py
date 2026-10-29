"""B14: the hosted compose override and the smoke scripts."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed")


@pytest.fixture(scope="module")
def prod() -> dict:
    out = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            "docker-compose.yml",
            "-f",
            "deploy/docker-compose.prod.yml",
            "config",
            "--format",
            "json",
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=True,
        env={**__import__("os").environ, "DOMAIN": "cashguard.example.ro"},
    )
    return json.loads(out.stdout)


def test_only_caddy_is_public(prod):
    for name in ("db", "keycloak", "api", "cron"):
        assert not prod["services"][name].get("ports"), name
    assert {p["published"] for p in prod["services"]["caddy"]["ports"]} == {"80", "443"}


def test_issuer_is_the_public_https_keycloak(prod):
    kc = prod["services"]["keycloak"]
    assert kc["environment"]["KC_HOSTNAME"] == "https://auth.cashguard.example.ro"
    assert kc["environment"]["KC_PROXY_HEADERS"] == "xforwarded"
    assert kc["command"][0] == "start"
    api = prod["services"]["api"]["environment"]
    assert api["KEYCLOAK_ISSUER"] == "https://auth.cashguard.example.ro/realms/cashguard"
    assert api["KEYCLOAK_INTERNAL_URL"] == "http://keycloak:8080/realms/cashguard"


def test_test_db_does_not_run_in_production(prod):
    assert "db-test" not in prod["services"]


def test_cron_runs_only_the_queue_jobs_by_default(prod):
    assert prod["services"]["cron"]["environment"]["CRON_ENABLED_JOBS"] == "process recover"


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_smoke_scripts_are_shellcheck_clean():
    scripts = [str(BACKEND / "scripts" / n) for n in ("smoke_local.sh", "smoke_remote.sh")]
    proc = subprocess.run(["shellcheck", "--shell=sh", *scripts], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout


def test_remote_smoke_needs_its_arguments():
    proc = subprocess.run(
        ["sh", "scripts/smoke_remote.sh"], cwd=BACKEND, capture_output=True, text=True
    )
    assert proc.returncode != 0 and "usage" in proc.stderr
