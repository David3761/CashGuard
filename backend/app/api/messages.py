from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.api import schemas as s
from app.api.deps import CurrentUser, Db
from app.services import messages

router = APIRouter(tags=["messages"])


@router.get("/messages")
async def list_messages(
    user: CurrentUser,
    db: Db,
    since: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> s.MessagesOut:
    rows = await messages.list_all(db, user.id, since=since, limit=limit)
    return s.MessagesOut(messages=[s.MessageOut(**r.model_dump()) for r in rows])
