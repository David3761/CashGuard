"""Run a time-based job for every user, each in its own unit of work (B11)."""

from datetime import date
from enum import StrEnum

from sqlalchemy import select

from app import clock
from app.db import models as m
from app.db.session import unit_of_work
from app.pipeline import jobs


class Job(StrEnum):
    CLOSE_DAY = "close-day"
    EXPIRE_EVENTS = "expire-events"
    EXPIRE_QUESTIONS = "expire-questions"
    RECEIVABLE_REMINDERS = "receivable-reminders"
    FORECAST_SNAPSHOT = "forecast-snapshot"
    WEEKLY_REFLECTION = "weekly-reflection"
    PREEMPTIVE = "preemptive"
    INFER_HYPOTHESES = "infer-hypotheses"


async def run(job: Job, user_id: int, day: date) -> None:
    async with unit_of_work() as db:
        now = clock.now()
        match job:
            case Job.CLOSE_DAY:
                await jobs.close_day(db, user_id, day)
            case Job.EXPIRE_EVENTS:
                await jobs.expire_events(db, user_id, now)
            case Job.EXPIRE_QUESTIONS:
                await jobs.expire_questions(db, user_id, now)
            case Job.RECEIVABLE_REMINDERS:
                await jobs.receivable_reminders(db, user_id, day)
            case Job.FORECAST_SNAPSHOT:
                await jobs.forecast_snapshot(db, user_id, day)
            case Job.WEEKLY_REFLECTION:
                await jobs.weekly_reflection(db, user_id, day)
            case Job.PREEMPTIVE:
                await jobs.preemptive(db, user_id, day)
            case Job.INFER_HYPOTHESES:
                await jobs.infer_hypotheses(db, user_id)


async def run_for_all(job: Job, day: date) -> int:
    async with unit_of_work() as db:
        user_ids = list(await db.scalars(select(m.User.id).order_by(m.User.id)))
    for user_id in user_ids:
        await run(job, user_id, day)
    return len(user_ids)


def day_sequence(day: date) -> list[Job]:
    """The sim order for closing `day` (arch §10): close → expire questions / events →
    reminders → (Mon) snapshot → (Sun) reflection + hypotheses."""
    order = [Job.CLOSE_DAY, Job.EXPIRE_QUESTIONS, Job.EXPIRE_EVENTS, Job.RECEIVABLE_REMINDERS]
    if day.weekday() == 0:
        order.append(Job.FORECAST_SNAPSHOT)
    if day.weekday() == 6:
        order += [Job.WEEKLY_REFLECTION, Job.INFER_HYPOTHESES]
    return order
