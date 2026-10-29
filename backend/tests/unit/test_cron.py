"""cron/run.sh, cron/crontab and cron/Dockerfile (B1, arch §10).

Runs the script with a fake `curl` on PATH.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]
RUN_SH = BACKEND / "cron" / "run.sh"
CRONTAB = BACKEND / "cron" / "crontab"
DOCKERFILE = BACKEND / "cron" / "Dockerfile"

TOKEN_URL = "http://keycloak:8080/realms/cashguard/protocol/openid-connect/token"
BASE_ENV = {
    "API_URL": "http://api:8000/api",
    "KEYCLOAK_TOKEN_URL": TOKEN_URL,
    "CRON_CLIENT_SECRET": "s3cret",
}

# arch §10: schedule → endpoint (Europe/Bucharest)
ARCH_SCHEDULE = {
    ("*/5 * * * *", "process"),
    ("*/5 * * * *", "recover"),
    ("55 23 * * *", "close-day"),
    ("0 9 * * *", "preemptive"),
    ("0 18 * * 0", "weekly-reflection"),
    ("0 3 * * *", "expire-events"),
    ("0 * * * *", "expire-questions"),
    ("0 10 * * *", "receivable-reminders"),
    ("0 0 * * 1", "forecast-snapshot"),
    ("0 20 * * 0", "infer-hypotheses"),
}

FAKE_CURL = """#!/bin/sh
# Records every call; answers the token request with a token, everything else with {}.
echo "$@" >> "$CURL_LOG"
for arg in "$@"; do
  case "$arg" in
    *openid-connect/token) [ -n "${FAIL_TOKEN:-}" ] && exit 22
                           echo '{"access_token":"tok123","expires_in":1800}'; exit 0 ;;
  esac
done
echo '{}'
"""


@pytest.fixture
def fake_path(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text(FAKE_CURL)
    curl.chmod(curl.stat().st_mode | stat.S_IEXEC)
    return bin_dir


def run(args, fake_path, tmp_path, **env):
    log = tmp_path / "curl.log"
    full_env = {"PATH": f"{fake_path}:{os.environ['PATH']}", "CURL_LOG": str(log)}
    full_env |= BASE_ENV | env
    proc = subprocess.run(
        ["sh", str(RUN_SH), *args], env=full_env, capture_output=True, text=True, check=False
    )
    calls = log.read_text().splitlines() if log.exists() else []
    return proc, calls


def test_run_dry_run_prints_url_and_calls_nothing(fake_path, tmp_path):
    proc, calls = run(["--dry-run", "process"], fake_path, tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.strip() == "POST http://api:8000/api/internal/process"
    assert calls == []


def test_run_gets_token_then_posts_with_bearer(fake_path, tmp_path):
    proc, calls = run(["close-day"], fake_path, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert len(calls) == 2
    assert TOKEN_URL in calls[0] and "client_credentials" in calls[0]
    assert "client_id=savings-cron" in calls[0]
    assert "-X POST" in calls[1]
    assert "Authorization: Bearer tok123" in calls[1]
    assert calls[1].endswith("http://api:8000/api/internal/close-day")


def test_run_token_failure_never_calls_the_endpoint(fake_path, tmp_path):
    proc, calls = run(["process"], fake_path, tmp_path, FAIL_TOKEN="1")
    assert proc.returncode != 0
    assert all("/internal/" not in c for c in calls)


def test_run_without_endpoint_fails(fake_path, tmp_path):
    proc, calls = run([], fake_path, tmp_path)
    assert proc.returncode != 0
    assert "usage" in proc.stderr
    assert calls == []


@pytest.mark.parametrize("bad", ["../health", "process;rm", "Process", "close_day", ""])
def test_run_rejects_endpoint_names_outside_lowercase_and_dashes(fake_path, tmp_path, bad):
    proc, calls = run([bad], fake_path, tmp_path)
    assert proc.returncode == 2
    assert "invalid endpoint" in proc.stderr
    assert calls == []


def test_run_missing_secret_fails_before_any_call(fake_path, tmp_path):
    proc, calls = run(["process"], fake_path, tmp_path, CRON_CLIENT_SECRET="")
    assert proc.returncode != 0
    assert "CRON_CLIENT_SECRET" in proc.stderr
    assert calls == []


def test_run_skips_jobs_not_in_enabled_list(fake_path, tmp_path):
    # Demo (Q21): only process/recover run on the clock; the simulator drives the day jobs.
    env = {"CRON_ENABLED_JOBS": "process recover"}
    proc, calls = run(["close-day"], fake_path, tmp_path, **env)
    assert proc.returncode == 0
    assert "skip close-day" in proc.stdout
    assert calls == []
    proc, calls = run(["recover"], fake_path, tmp_path, **env)
    assert proc.returncode == 0 and len(calls) == 2


def crontab_entries() -> set[tuple[str, str]]:
    entries = set()
    for line in CRONTAB.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        fields = line.split()
        schedule, command = " ".join(fields[:5]), fields[5:]
        assert command[0] == "/cron/run.sh", line
        entries.add((schedule, command[1]))
    return entries


def test_crontab_matches_arch_schedule():
    assert crontab_entries() == ARCH_SCHEDULE


def test_crontab_leaves_job_output_to_supercronic():
    # supercronic logs each job's output to the container log; a redirect to PID 1's stdout
    # (the busybox crond trick) is not needed and fails for an unprivileged user.
    for line in CRONTAB.read_text().splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            assert ">" not in line, line


def test_cron_image_runs_supercronic_unprivileged():
    instructions = [
        line.strip() for line in DOCKERFILE.read_text().splitlines() if line.strip()[:1] not in "#"
    ]
    assert "USER 10001" in instructions
    assert not any(line.startswith("USER root") or line == "USER 0" for line in instructions)
    assert instructions[-1].startswith('CMD ["supercronic"')
    assert '"/cron/crontab"]' in instructions[-1]
    assert any("sha1sum -c" in line for line in instructions)  # the download is verified
    assert "crond" not in DOCKERFILE.read_text()


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed")
def test_cron_scripts_are_shellcheck_clean():
    scripts = sorted((BACKEND / "cron").glob("*.sh"))
    assert scripts
    proc = subprocess.run(
        ["shellcheck", "--shell=sh", *map(str, scripts)], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stdout
