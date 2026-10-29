"""GET /state: the dashboard snapshot (arch 9.3)."""

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select

from app import clock
from app.api import schemas as s
from app.api.deps import CurrentUser, Db
from app.api.views import plan_out, streak_days
from app.db import models as m
from app.services import notifications
from app.services.agent_events import open_question
from app.services.context_loader import load_user_context

router = APIRouter(tags=["state"])


@router.get("/state")
async def get_state(user: CurrentUser, db: Db) -> s.State:
    today = clock.today()
    ctx = await load_user_context(db, user.id, today, history_days=1)
    onboarded = user.onboarded_at is not None
    goal = plan = forecast = None
    if onboarded and ctx.goal is not None:
        saved = ctx.goal_pot.saved if ctx.goal_pot else Decimal("0")
        goal = s.GoalOut(
            amount=ctx.goal.amount,
            deadline=ctx.goal.deadline,
            motivation=ctx.goal.motivation,
            progress_pct=round(float(saved / ctx.goal.amount * 100), 1),
            days_left=max((ctx.goal.deadline - today).days, 0),
        )
    if onboarded and ctx.plan is not None:
        plan = await plan_out(db, user.id, ctx.plan, today)
    if onboarded and ctx.forecast is not None:
        forecast = s.ForecastOut(**ctx.forecast.model_dump(include=set(s.ForecastOut.model_fields)))
    question = await open_question(db, user.id)
    pending = None
    if question is not None:
        message_id = await db.scalar(
            select(m.Message.id)
            .where(m.Message.agent_event_id == question.id)
            .order_by(m.Message.id.desc())
            .limit(1)
        )
        pending = s.PendingQuestion(
            agent_event_id=question.id,
            transaction_id=question.ref_transaction_id,
            message_id=message_id,
        )
    return s.State(
        date=today,
        account=s.AccountOut(**ctx.account.model_dump()),
        onboarding=s.Onboarding(
            goal=ctx.goal is not None,
            income=bool(ctx.income_sources),
            fixed_costs=bool(ctx.fixed_costs),
            life_context=bool(ctx.facts),
            done=onboarded,
        ),
        goal=goal,
        plan=plan,
        upcoming_events=[
            s.EventOut(**e.model_dump(include={"id", "name", "date", "est_cost"}))
            for e in ctx.life_events[:10]
        ],
        streak_days=await streak_days(db, user.id, today),
        unread_notifications=await notifications.unread_count(db, user.id),
        forecast=forecast,
        pots=[s.PotOut(**p.model_dump(include=set(s.PotOut.model_fields))) for p in ctx.pots],
        receivables=s.ReceivablesSummary(
            open_total=sum((r.amount for r in ctx.receivables), Decimal("0")),
            items=[
                s.ReceivableItem(**r.model_dump(include=set(s.ReceivableItem.model_fields)))
                for r in ctx.receivables
            ],
        ),
        pending_question=pending,
        last_plan_change=ctx.plan.reason if ctx.plan else None,
    )
