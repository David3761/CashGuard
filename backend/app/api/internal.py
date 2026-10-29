"""Cron-only endpoints (`internal` role) (B8 step 4; B11 adds the day jobs)."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app import clock
from app.auth import Claims, require_internal
from app.pipeline import day_jobs
from app.pipeline.processor import process_user, recover_stale, users_with_work

router = APIRouter(prefix="/internal", tags=["internal"])
Internal = Annotated[Claims, Depends(require_internal)]


@router.post("/process")
async def process(_: Internal) -> dict[str, int]:
    """Process every user with unresolved transactions."""
    users = await users_with_work()
    resolved = 0
    for user_id in users:
        resolved += (await process_user(user_id, "cron")).resolved
    return {"users": len(users), "resolved": resolved}


@router.post("/recover")
async def recover(_: Internal) -> dict[str, int]:
    """Reset `processing` rows stuck for more than 5 minutes."""
    return {"recovered": await recover_stale()}


@router.post("/{job}")
async def run_day_job(job: day_jobs.Job, _: Internal) -> dict[str, int]:
    """close-day, expire-events, expire-questions, receivable-reminders, forecast-snapshot,
    weekly-reflection, preemptive, infer-hypotheses (cron schedules them, arch §10)."""
    return {"users": await day_jobs.run_for_all(job, clock.today())}
