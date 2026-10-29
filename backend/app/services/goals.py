"""Goals: one active goal per user (D17) (B3 step 1)."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clock
from app.db import models as m
from app.domain import models as dm
from app.domain.enums import GoalStatus, PotKind, PotStatus
from app.errors import DomainError
from app.services._common import invalid, invalid_transition, owned, unique_or, view

GOAL_ALREADY_ACTIVE = DomainError(
    "goal_already_active", "There is already an active goal; update it instead.", status=409
)


def _check(amount: Decimal | None, deadline: date | None) -> None:
    if amount is not None and amount <= 0:
        raise invalid("invalid_amount", "The goal amount must be positive.")
    if deadline is not None and deadline < clock.today():
        raise invalid("deadline_passed", "The deadline is in the past.")


async def _goal_pot(db: AsyncSession, goal_id: int) -> m.Pot | None:
    return await db.scalar(
        select(m.Pot).where(m.Pot.goal_id == goal_id, m.Pot.kind == PotKind.GOAL)
    )


async def get(db: AsyncSession, user_id: int, goal_id: int) -> dm.Goal:
    """One goal. Another user's → not_found."""
    return view(dm.Goal, await owned(db, m.Goal, user_id, goal_id, "Goal"))


async def get_active(db: AsyncSession, user_id: int) -> dm.Goal | None:
    """The active goal, or None (onboarding, after goal_completed)."""
    row = await db.scalar(
        select(m.Goal).where(m.Goal.user_id == user_id, m.Goal.status == GoalStatus.ACTIVE)
    )
    return view(dm.Goal, row) if row is not None else None


async def create(
    db: AsyncSession,
    user_id: int,
    *,
    amount: Decimal,
    deadline: date,
    motivation: str | None = None,
    soft: bool = True,
) -> dm.Goal:
    """A new active goal + its goal pot. Already one active → goal_already_active (409)."""
    _check(amount, deadline)
    if await get_active(db, user_id) is not None:
        raise GOAL_ALREADY_ACTIVE
    goal = m.Goal(
        user_id=user_id, amount=amount, deadline=deadline, motivation=motivation, soft=soft
    )

    async def insert() -> m.Goal:
        db.add(goal)
        await db.flush()
        db.add(
            m.Pot(
                user_id=user_id,
                name=motivation or "Obiectiv",
                kind=PotKind.GOAL,
                goal_id=goal.id,
                target=amount,
                deadline=deadline,
            )
        )
        await db.flush()
        return goal

    return view(dm.Goal, await unique_or(db, insert, GOAL_ALREADY_ACTIVE))


async def update(
    db: AsyncSession,
    user_id: int,
    goal_id: int,
    *,
    amount: Decimal | None = None,
    deadline: date | None = None,
    motivation: str | None = None,
    soft: bool | None = None,
) -> dm.Goal:
    """Change only the fields given. A completed goal → invalid_transition."""
    goal = await owned(db, m.Goal, user_id, goal_id, "Goal")
    if goal.status != GoalStatus.ACTIVE:
        raise invalid_transition("The goal", goal.status, "changed")
    _check(amount, deadline)
    pot = await _goal_pot(db, goal.id)
    if amount is not None:
        goal.amount = amount
        if pot is not None:
            pot.target = amount
    if deadline is not None:
        goal.deadline = deadline
        if pot is not None:
            pot.deadline = deadline
    if motivation is not None:
        goal.motivation = motivation
    if soft is not None:
        goal.soft = soft
    await db.flush()
    return view(dm.Goal, goal)


async def complete(db: AsyncSession, user_id: int, goal_id: int) -> dm.Goal:
    """active → completed. Already completed → invalid_transition."""
    goal = await owned(db, m.Goal, user_id, goal_id, "Goal")
    if goal.status != GoalStatus.ACTIVE:
        raise invalid_transition("The goal", goal.status, GoalStatus.COMPLETED)
    goal.status = GoalStatus.COMPLETED
    pot = await _goal_pot(db, goal.id)
    if pot is not None and pot.status == PotStatus.ACTIVE:
        pot.status = PotStatus.COMPLETED
    await db.flush()
    return view(dm.Goal, goal)
