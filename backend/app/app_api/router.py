"""The app API: David V.'s Flutter contract (API_SPEC.md), at the root, next to `/api`.

    GET    /balance                 {"balance": <bani>, "currency": "RON"}
    GET    /transactions            {"transactions": [{id, title, amount, type, created_at}]}
    POST   /devices                 {fcm_token, platform} → the stored device (idempotent)
    DELETE /devices/{fcm_token}     {}
    GET    /assistant/messages      {"messages": [{id, text, sender, created_at}]}
    POST   /assistant/messages      {"text"} → SSE: message → delta* → done | error

No auth (one demo user, `APP_API_USER`); errors are `{"message"}`. Mounted only when
`APP_API_ENABLED` (off in code, on in `.env.example`). Abuse protection on the chat
(app.security.ratelimit): the `chat` bucket keyed by the one principal "app" (behind Caddy the
client IP says nothing), a text limit, and one reply at a time per user.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.deps import Db
from app.app_api import chat, sse
from app.app_api.errors import AppError, MessageErrorRoute
from app.app_api.mapping import (
    SAVINGS_TITLE,
    TRANSFER_ID_OFFSET,
    iso_utc,
    message_json,
    signed_bani,
    to_bani,
    transaction_title,
    transaction_type,
)
from app.app_api.schemas import (
    BalanceOut,
    DeviceIn,
    DeviceOut,
    Empty,
    MessageIn,
    MessageOut,
    MessagesOut,
    TransactionOut,
    TransactionsOut,
)
from app.app_api.user import AppUser, resolve_app_user
from app.config import Settings, get_app_settings
from app.db import models as m
from app.db.session import unit_of_work
from app.domain.enums import AgentTrigger, InputMode
from app.errors import DomainError
from app.pipeline import ports
from app.security import ratelimit
from app.security.ratelimit import app_key, rate_limited
from app.services import accounts, agent_runs, devices, messages, transactions, users

BUSY = "The assistant is still answering your previous message."
EMPTY_TEXT = "Write a message first."
TOO_LONG = "Your message is too long (at most {limit} characters)."


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
RunnerDep = Annotated[chat.ReplyRunner, Depends(chat.get_reply_runner)]


async def _app_user(db: Db, settings: SettingsDep) -> AppUser:
    return await resolve_app_user(db, settings)


UserDep = Annotated[AppUser, Depends(_app_user)]

router = APIRouter(
    route_class=MessageErrorRoute,
    tags=["app"],
    responses={"default": {"model": AppError, "description": 'Any failure: {"message": "..."}'}},
)


@router.get("/balance")
async def get_balance(user: UserDep, db: Db) -> BalanceOut:
    account = await accounts.get(db, user.id)
    return BalanceOut(balance=to_bani(account.current_balance))


@router.get("/transactions")
async def get_transactions(user: UserDep, db: Db) -> TransactionsOut:
    """Transactions and savings transfers, newest first."""
    feed: list[tuple[datetime, int, TransactionOut]] = []
    for tx in await transactions.list_all(db, user.id):
        out = TransactionOut(
            id=tx.id,
            title=transaction_title(tx.merchant, tx.merchant_raw, tx.mcc),
            amount=signed_bani(tx.amount, tx.direction),
            type=transaction_type(tx.direction, tx.category),
            created_at=iso_utc(tx.occurred_at),
        )
        feed.append((tx.occurred_at, tx.id, out))
    rows = await db.execute(
        select(m.Transfer, m.Pot.name)
        .outerjoin(m.Pot, m.Pot.id == m.Transfer.pot_id)
        .where(m.Transfer.user_id == user.id, m.Transfer.undone_at.is_(None))
    )
    fallback_title = SAVINGS_TITLE.get(user.language, SAVINGS_TITLE["ro"])
    for transfer, pot_name in rows.all():
        shown_id = TRANSFER_ID_OFFSET + transfer.id
        out = TransactionOut(
            id=shown_id,
            title=(pot_name or "").strip() or fallback_title,
            amount=-to_bani(transfer.amount),
            type="transfer_out",
            created_at=iso_utc(transfer.created_at),
        )
        feed.append((transfer.created_at, shown_id, out))
    feed.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return TransactionsOut(transactions=[out for _, _, out in feed])


@router.post("/devices")
async def register_device(
    body: DeviceIn, user: UserDep, db: Db, settings: SettingsDep
) -> DeviceOut:
    row = await devices.upsert(
        db, user.sub, body.fcm_token, body.platform, keep=settings.APP_API_MAX_DEVICES
    )
    await db.commit()
    return DeviceOut(fcm_token=row.fcm_token, platform=m.DevicePlatform(row.platform))


@router.delete("/devices/{fcm_token}")
async def unregister_device(fcm_token: str, user: UserDep, db: Db) -> Empty:
    await devices.remove(db, user.sub, fcm_token)
    await db.commit()
    return Empty()


@router.get("/assistant/messages")
async def get_messages(user: UserDep, db: Db, settings: SettingsDep) -> MessagesOut:
    rows = await messages.recent(db, user.id, limit=settings.APP_API_HISTORY_LIMIT)
    return MessagesOut(messages=[MessageOut.model_validate(message_json(r)) for r in rows])


def guard_key(user_id: int) -> str:
    """One reply at a time per user (shared with nothing else; agent_runs covers /api/chat)."""
    return f"app-chat:{user_id}"


@router.post(
    "/assistant/messages",
    dependencies=[Depends(rate_limited("chat", key=app_key))],
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "SSE: `message`, then `delta`*, then `done` or `error`",
            "content": {"text/event-stream": {}},
        }
    },
)
async def post_message(
    body: MessageIn,
    settings: SettingsDep,
    runner: RunnerDep,
) -> StreamingResponse:
    text = body.text.strip()
    if not text:
        raise DomainError("empty_text", EMPTY_TEXT, status=422)
    if len(text) > settings.APP_API_MAX_TEXT_CHARS:
        raise DomainError(
            "text_too_long", TOO_LONG.format(limit=settings.APP_API_MAX_TEXT_CHARS), status=422
        )
    async with unit_of_work() as db:
        user = await resolve_app_user(db, settings)
    # Claimed here and released by the reply task when the run ends (it outlives the request),
    # so this is the guard's claim/release rather than the `one_at_a_time` block.
    guard, key = ratelimit.guard(), guard_key(user.id)
    if not guard.claim(key):
        raise DomainError("agent_busy", BUSY, status=409)
    try:
        async with unit_of_work() as db:
            if await agent_runs.is_running(db, user.id):
                raise DomainError("agent_busy", BUSY, status=409)
            stored = await messages.save_user(db, user.id, text, InputMode.TEXT)
            profile = await users.get(db, user.id)
            language = ports.detect_language(text, profile.language)
            if language != profile.language:
                await users.update(db, user.id, language=language)
            run_id = await agent_runs.start(
                db, user.id, trigger=AgentTrigger.CHAT, model=settings.ANTHROPIC_MODEL
            )
    except BaseException:
        guard.release(key)
        raise
    task = chat.start_reply(user.id, run_id, text, runner, release=lambda: guard.release(key))
    return StreamingResponse(
        chat.stream_reply(stored, task, timeout_s=settings.APP_API_REPLY_TIMEOUT_S),
        media_type=sse.MEDIA_TYPE,
        headers=sse.HEADERS,
    )


def install_app_api(app: FastAPI, settings: Settings) -> None:
    """Mount the routes, the CORS policy and the FCM push bridge; (re)build the rate limits from
    these settings (create_app may already have done it: the result is the same)."""
    ratelimit.configure(settings)
    app.include_router(router)
    from app.push import bridge, fcm

    bridge.install(bridge.PushBridge(fcm.sender_from_settings(settings)))
    cors: dict[str, Any] = {
        "allow_origin_regex": settings.APP_API_CORS_ORIGIN_REGEX,
        "allow_methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Accept", "Authorization"],
        "expose_headers": ["Retry-After"],
        "allow_credentials": False,
    }
    if settings.APP_API_CORS_ORIGIN_REGEX:
        app.add_middleware(CORSMiddleware, **cors)
