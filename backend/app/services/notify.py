"""`notify`: a templated notification in the user's language, pushed after the commit (B13)."""

from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.domain import models as dm
from app.i18n.notifications import TEMPLATES
from app.pipeline import ports
from app.services import notifications, users
from app.services._common import invalid
from app.ws import push_after_commit


def render(type_: str, params: dict[str, Any], language: str) -> tuple[str, str]:
    """(title, body) with money formatted for the language (Decimal values are money)."""
    template = TEMPLATES.get(type_)
    if template is None:
        raise invalid("unknown_notification", f"No template for {type_!r}.")
    shown = {
        k: ports.format_money(v, language) if isinstance(v, Decimal) else v
        for k, v in params.items()
    }
    title, body = template.en if language == "en" else template.ro
    return title.format(**shown), body.format(**shown)


async def notify(
    db: AsyncSession,
    user_id: int,
    type_: str,
    params: dict[str, Any] | None = None,
    *,
    agent_event_id: int | None = None,
    message_id: int | None = None,
) -> dm.NotificationView:
    """Create the row and push `notification.new` once the session commits."""
    user = await users.get(db, user_id)
    title, body = render(type_, params or {}, user.language)
    row = await notifications.create(
        db,
        user_id,
        type=type_,
        title=title,
        body=body,
        opens_chat=TEMPLATES[type_].opens_chat,
        agent_event_id=agent_event_id,
        message_id=message_id,
    )
    push_after_commit(db, user_id, events.notification_new(row))
    return row
