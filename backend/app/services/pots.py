"""Named savings pots; the goal has its own (arch 4.4) (B3 step 4)."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import case, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import models as m
from app.domain import models as dm
from app.domain.enums import GoalStatus, PotKind, PotStatus
from app.errors import DomainError
from app.services._common import as_enum, invalid, invalid_transition, owned, view


def _check(target: Decimal | None, monthly_contribution: Decimal | None) -> None:
    if target is not None and target <= 0:
        raise invalid("invalid_amount", "A pot needs a positive target.")
    if monthly_contribution is not None and monthly_contribution < 0:
        raise invalid("invalid_amount", "The monthly contribution can't be negative.")


async def get(db: AsyncSession, user_id: int, pot_id: int) -> dm.Pot:
    """One pot. Another user's → not_found."""
    return view(dm.Pot, await owned(db, m.Pot, user_id, pot_id, "Pot"))


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    name: str,
    kind: PotKind,
    target: Decimal,
    deadline: date | None = None,
    goal_id: int | None = None,
    life_event_id: int | None = None,
    fact_id: int | None = None,
    monthly_contribution: Decimal = Decimal("0"),
) -> dm.Pot:
    """An active pot (saved 0)."""
    _check(target, monthly_contribution)
    row = m.Pot(
        user_id=user_id,
        name=name,
        kind=as_enum(PotKind, kind, "invalid_pot_kind"),
        target=target,
        deadline=deadline,
        goal_id=goal_id,
        life_event_id=life_event_id,
        fact_id=fact_id,
        monthly_contribution=monthly_contribution,
    )
    db.add(row)
    await db.flush()
    return view(dm.Pot, row)


async def update(
    db: AsyncSession,
    user_id: int,
    pot_id: int,
    *,
    name: str | None = None,
    target: Decimal | None = None,
    deadline: date | None = None,
    monthly_contribution: Decimal | None = None,
) -> dm.Pot:
    """Change only the fields given. A closed pot → invalid_transition."""
    _check(target, monthly_contribution)
    row = await owned(db, m.Pot, user_id, pot_id, "Pot")
    if row.status == PotStatus.CLOSED:
        raise invalid_transition("The pot", row.status, "changed")
    if name is not None:
        row.name = name
    if target is not None:
        row.target = target
    if deadline is not None:
        row.deadline = deadline
    if monthly_contribution is not None:
        row.monthly_contribution = monthly_contribution
    await db.flush()
    return view(dm.Pot, row)


async def close(db: AsyncSession, user_id: int, pot_id: int) -> dm.Pot:
    """active | completed → closed. Already closed → invalid_transition."""
    row = await owned(db, m.Pot, user_id, pot_id, "Pot")
    if row.status == PotStatus.CLOSED:
        raise invalid_transition("The pot", row.status, PotStatus.CLOSED)
    row.status = PotStatus.CLOSED
    await db.flush()
    return view(dm.Pot, row)


async def list_active(db: AsyncSession, user_id: int) -> Sequence[dm.Pot]:
    """Active pots, the goal pot first."""
    goal_first = case((m.Pot.kind == PotKind.GOAL, 0), else_=1)
    rows = await db.scalars(
        select(m.Pot)
        .where(m.Pot.user_id == user_id, m.Pot.status == PotStatus.ACTIVE)
        .order_by(goal_first, m.Pot.created_at, m.Pot.id)
    )
    return [view(dm.Pot, r) for r in rows]


async def goal_pot(db: AsyncSession, user_id: int) -> dm.Pot | None:
    """The active goal's pot, or None."""
    row = await db.scalar(
        select(m.Pot)
        .join(m.Goal, m.Goal.id == m.Pot.goal_id)
        .where(
            m.Pot.user_id == user_id, m.Pot.kind == PotKind.GOAL, m.Goal.status == GoalStatus.ACTIVE
        )
    )
    return view(dm.Pot, row) if row is not None else None


async def add_saved(db: AsyncSession, user_id: int, pot_id: int, delta: Decimal) -> dm.Pot:
    """saved += delta atomically (negative when a pot pays for something). Below 0 →
    insufficient_pot_balance (409). Keeps `accounts.savings_pot` equal to the goal pot."""
    pot = await owned(db, m.Pot, user_id, pot_id, "Pot")
    result = await db.execute(
        sql_update(m.Pot)
        .where(m.Pot.id == pot_id, m.Pot.saved + delta >= 0)
        .values(saved=m.Pot.saved + delta)
        .returning(m.Pot.saved)
        .execution_options(synchronize_session="fetch")
    )
    saved = result.scalar_one_or_none()
    if saved is None:
        raise DomainError(
            "insufficient_pot_balance", f"The pot has only {pot.saved} lei.", status=409
        )
    if pot.kind == PotKind.GOAL:
        await db.execute(
            sql_update(m.Account)
            .where(m.Account.user_id == user_id)
            .values(savings_pot=saved)
            .execution_options(synchronize_session="fetch")
        )
    await db.refresh(pot)
    return view(dm.Pot, pot)
