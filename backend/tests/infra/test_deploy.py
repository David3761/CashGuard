"""B14: the hosted compose override and the smoke scripts."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(shutil.which("docker") is None, reason="docker CLI not installed")


# The secrets the hosted overlay requires (`${VAR:?}`): dummy values for `config` to render.
PROD_SECRETS = {
    "POSTGRES_PASSWORD": "pg-secret",
    "KC_DB_PASSWORD": "kc-db-secret",
    "KC_ADMIN_USER": "ops",
    "KC_ADMIN_PASSWORD": "kc-admin-secret",
    "KC_CRON_CLIENT_SECRET": "cron-secret",
    "KC_DEMO_PASSWORD": "demo-password-long",
    "APP_API_KEY": "app-key-secret",
}


def prod_config(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """`docker compose config` of base + prod overlay with exactly `env` (no shell variables,
    no backend/.env: `--env-file /dev/null`), so a missing secret can't be filled in by luck."""
    return subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "/dev/null",
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
        check=False,
        env={"PATH": os.environ["PATH"], "HOME": os.environ.get("HOME", str(BACKEND)), **env},
    )


@pytest.fixture(scope="module")
def prod() -> dict:
    out = prod_config({"DOMAIN": "cashguard.example.ro", **PROD_SECRETS})
    assert out.returncode == 0, out.stderr
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


# ── security review P0-1 / P0-2 / P1-5 / P1-8 / P1-10 / P1-11 ─────────────────────────────────


@pytest.mark.parametrize("missing", sorted(PROD_SECRETS))
def test_prod_overlay_requires_every_secret(missing):
    env = {"DOMAIN": "cashguard.example.ro", **PROD_SECRETS}
    del env[missing]
    out = prod_config(env)
    assert out.returncode != 0
    assert missing in out.stderr


def test_prod_uses_the_given_secrets_never_the_dev_defaults(prod):
    s = prod["services"]
    kc = s["keycloak"]["environment"]
    assert kc["KC_BOOTSTRAP_ADMIN_USERNAME"] == "ops"
    assert kc["KC_BOOTSTRAP_ADMIN_PASSWORD"] == "kc-admin-secret"
    assert kc["KC_CRON_CLIENT_SECRET"] == s["cron"]["environment"]["CRON_CLIENT_SECRET"]
    assert kc["KC_DEMO_PASSWORD"] == "demo-password-long"
    assert kc["KC_DB_PASSWORD"] == s["db"]["environment"]["KC_DB_PASSWORD"] == "kc-db-secret"
    assert s["db"]["environment"]["POSTGRES_PASSWORD"] == "pg-secret"
    assert s["api"]["environment"]["DATABASE_URL"] == (
        "postgresql+psycopg://cashguard:pg-secret@db:5432/cashguard"
    )
    assert s["api"]["environment"]["APP_API_KEY"] == "app-key-secret"  # the app API's X-App-Key


def test_prod_api_docs_off_sim_explicit_and_caddy_trusted(prod):
    api = prod["services"]["api"]["environment"]
    assert api["API_DOCS_ENABLED"] == "false"
    assert api["SIM_MODE"] == "true"  # the hosted demo; /api/sim/* needs the realm role `sim`
    assert api["FORWARDED_ALLOW_IPS"] == "*"  # only Caddy can reach the api (no public port)


def test_caddy_hides_the_keycloak_admin_console():
    caddy = (BACKEND / "deploy" / "Caddyfile").read_text()
    auth = caddy[caddy.index("auth.{$DOMAIN}") :]
    assert "@admin path /admin /admin/*" in auth
    assert "respond @admin 404" in auth
    assert auth.index("respond @admin 404") < auth.index("reverse_proxy keycloak:8080")
    api = caddy[caddy.index("api.{$DOMAIN}") : caddy.index("auth.{$DOMAIN}")]
    assert "max_size 64KB" in api
    assert "Strict-Transport-Security" in caddy


UVICORN_FLAGS = (
    "--proxy-headers",
    "--forwarded-allow-ips",
    "--no-server-header",
    "--ws-max-size 65536",
)


def test_api_dockerfile_runs_unprivileged_with_a_healthcheck_and_hardened_uvicorn():
    dockerfile = (BACKEND / "Dockerfile").read_text()
    users = [line.split()[1] for line in dockerfile.splitlines() if line.startswith("USER ")]
    assert users and users[-1] not in {"root", "0"}
    assert "HEALTHCHECK" in dockerfile and "/api/health" in dockerfile
    cmd = next(line for line in dockerfile.splitlines() if line.startswith("CMD "))
    assert "--workers 1" in cmd
    for flag in UVICORN_FLAGS:
        assert flag in cmd, flag


def test_compose_api_command_has_the_same_uvicorn_flags(prod):
    # the compose command overrides the Dockerfile CMD: both must carry the flags
    command = " ".join(prod["services"]["api"]["command"])
    assert "--workers 1" in command
    for flag in UVICORN_FLAGS:
        assert flag in command, flag


def test_containers_cannot_gain_privileges(prod):
    for name in ("api", "cron"):
        assert "no-new-privileges:true" in prod["services"][name]["security_opt"], name


def test_cron_dockerfile_explains_why_it_runs_as_root():
    dockerfile = (BACKEND / "cron" / "Dockerfile").read_text()
    assert "nosemgrep: dockerfile.security.missing-user.missing-user" in dockerfile
    assert "HEALTHCHECK" in dockerfile
