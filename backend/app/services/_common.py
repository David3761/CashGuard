"""Shared by the services: ownership checks, ORM → domain conversion, error helpers."""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Base
from app.errors import DomainError


def not_found(what: str) -> DomainError:
    return DomainError("not_found", f"{what} not found.", status=404)


def invalid(code: str, message: str) -> DomainError:
    return DomainError(code, message, status=422)


def invalid_transition(what: str, current: str, wanted: str) -> DomainError:
    return DomainError(
        "invalid_transition", f"{what} is {current}; it can't become {wanted}.", status=409
    )


async def owned[RowT: Base](
    db: AsyncSession, model: type[RowT], user_id: int, row_id: int, what: str
) -> RowT:
    """The row if it belongs to `user_id`; otherwise not_found (never forbidden: don't leak that
    it exists)."""
    columns = model.__table__.c
    stmt = select(model).where(columns.id == row_id, columns.user_id == user_id)
    row = (await db.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise not_found(what)
    return row


def view[ModelT: BaseModel](model: type[ModelT], row: Any) -> ModelT:
    """An ORM row as a frozen domain object (field names match the columns)."""
    return model.model_validate(row, from_attributes=True)


def as_enum[EnumT: StrEnum](enum: type[EnumT], value: Any, code: str) -> EnumT:
    try:
        return enum(value)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in enum)
        raise invalid(code, f"{value!r} is not one of: {allowed}.") from exc


async def unique_or[T](
    db: AsyncSession, action: Callable[[], Awaitable[T]], error: DomainError
) -> T:
    """Run `action` in a SAVEPOINT; a unique-constraint violation becomes `error` and the
    caller's session stays usable."""
    try:
        async with db.begin_nested():
            return await action()
    except IntegrityError as exc:
        raise error from exc
