from fastapi import APIRouter

from app import clock
from app.api import schemas as s
from app.api.deps import CurrentUser, Db
from app.api.views import plan_out
from app.services import plans
from app.services._common import not_found

router = APIRouter(tags=["plan"])


@router.get("/plan")
async def get_plan(user: CurrentUser, db: Db) -> s.PlanOut:
    plan = await plans.latest(db, user.id)
    if plan is None:
        raise not_found("Plan")
    return await plan_out(db, user.id, plan, clock.today())


@router.get("/plan/history")
async def plan_history(user: CurrentUser, db: Db) -> s.PlanHistory:
    return s.PlanHistory(
        versions=[
            s.PlanVersion(
                version=p.version,
                created_at=p.created_at,
                feasible=p.feasible,
                today_budget=p.today_budget,
            )
            for p in await plans.history(db, user.id)
        ]
    )
