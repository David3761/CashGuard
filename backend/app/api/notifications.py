from fastapi import APIRouter, Response
from pydantic import AwareDatetime

from app.api import schemas as s
from app.api.deps import CurrentUser, Db
from app.services import notifications

router = APIRouter(tags=["notifications"])


@router.get("/notifications")
async def list_notifications(
    user: CurrentUser, db: Db, since: AwareDatetime | None = None, unread_only: bool = False
) -> s.NotificationsOut:
    rows = await notifications.list_all(db, user.id, since=since, unread_only=unread_only)
    return s.NotificationsOut(
        notifications=[
            s.NotificationOut(**r.model_dump(include=set(s.NotificationOut.model_fields)))
            for r in rows
        ]
    )


@router.post("/notifications/{notification_id}/read", status_code=204)
async def read_notification(notification_id: int, user: CurrentUser, db: Db) -> Response:
    await notifications.mark_read(db, user.id, notification_id)
    await db.commit()
    return Response(status_code=204)
