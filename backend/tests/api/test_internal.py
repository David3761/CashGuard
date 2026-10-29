"""B8 step 4: /internal/process and /internal/recover need the `internal` role."""

import pytest


@pytest.mark.parametrize("path", ["/internal/process", "/internal/recover"])
async def test_internal_endpoints_need_the_role(as_user, path):
    r = await as_user("someone").post(path)
    assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden"


@pytest.mark.parametrize("path", ["/internal/process", "/internal/recover"])
async def test_internal_endpoints_without_a_token(client, path):
    assert (await client.post(path)).status_code == 401


@pytest.mark.parametrize(
    "job",
    [
        "close-day",
        "expire-events",
        "expire-questions",
        "receivable-reminders",
        "forecast-snapshot",
        "weekly-reflection",
        "preemptive",
        "infer-hypotheses",
    ],
)
async def test_day_job_endpoints_need_the_role(as_user, job):
    assert (await as_user("someone").post(f"/internal/{job}")).status_code == 403


async def test_day_job_endpoint_runs_for_cron(as_committed_user, db_committed):
    from tests import factories as f

    await f.user(db_committed)
    await db_committed.commit()
    r = await as_committed_user("cron", roles=("internal",)).post("/internal/close-day")
    assert r.status_code == 200 and r.json() == {"users": 1}
    assert (
        await as_committed_user("cron", roles=("internal",)).post("/internal/nope")
    ).status_code == 422
