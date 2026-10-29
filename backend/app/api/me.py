from fastapi import APIRouter

from app.api.deps import CurrentUser, Db
from app.api.schemas import Me, MePatch
from app.domain.models import UserProfile
from app.services import users

router = APIRouter(tags=["me"])


def me_out(user: UserProfile) -> Me:
    return Me(
        user_id=user.id,
        name=user.name,
        language=user.language,
        coach_style=user.coach_style,
        onboarded=user.onboarded_at is not None,
    )


@router.get("/me")
async def get_me(user: CurrentUser) -> Me:
    return me_out(user)


@router.patch("/me")
async def patch_me(body: MePatch, user: CurrentUser, db: Db) -> Me:
    updated = await users.update(db, user.id, language=body.language, coach_style=body.coach_style)
    await db.commit()
    return me_out(updated)
