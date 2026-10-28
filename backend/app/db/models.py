"""Every table of arch §4 (4.1 + 4.2 + 4.4) and plan_preferences (6.7).

Conventions (B2): money NUMERIC(12,2); JSON as JSONB; times timestamptz from `app.clock.now()`
(never the DB clock: the simulator owns "now"); enums as text + CHECK generated from
`app.domain.enums`, so adding a value there is the only change. Deleting a user removes every
row it owns (ON DELETE CASCADE), which `/sim/reset` relies on.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app import clock
from app.domain import enums as e

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

Money = Numeric(12, 2)
Score = Numeric(5, 4)  # 0–1 scores and confidences, 4 decimals


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def enum_check(column: str, enum: type[StrEnum]) -> CheckConstraint:
    """`column IN ('a', 'b', …)`; NULL passes (nullable columns stay optional)."""
    values = ", ".join(f"'{member.value}'" for member in enum)
    return CheckConstraint(f"{column} IN ({values})", name=column)


def _now() -> datetime:
    return clock.now()


def user_fk() -> Any:
    return ForeignKey("users.id", ondelete="CASCADE")


def created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=_now, nullable=False)


# ── 4.1 / 4.2: profile & plan inputs ──────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        enum_check("language", e.Language),
        enum_check("coach_style", e.CoachStyle),
        CheckConstraint("household_scale >= 1", name="household_scale"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    keycloak_sub: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    age: Mapped[int | None]
    language: Mapped[str] = mapped_column(String(2), default=e.Language.RO)
    coach_style: Mapped[str] = mapped_column(String(10), default=e.CoachStyle.WARM)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Bucharest")
    city: Mapped[str | None] = mapped_column(String(100))
    household_scale: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=Decimal("1.00"))
    onboarded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = created_at()


class Account(Base):
    __tablename__ = "accounts"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    current_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    # kept for compatibility: mirrors the goal pot's `saved` (arch 4.4)
    savings_pot: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        enum_check("status", e.GoalStatus),
        CheckConstraint("amount > 0", name="amount_positive"),
        # one active goal per user (D17)
        Index(
            "uq_goals_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    amount: Mapped[Decimal] = mapped_column(Money)
    deadline: Mapped[date] = mapped_column(Date)
    motivation: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), default=e.GoalStatus.ACTIVE)
    created_at: Mapped[datetime] = created_at()


class IncomeSource(Base):
    __tablename__ = "income_sources"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="day_of_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    source: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Money)
    day_of_month: Mapped[int] = mapped_column(Integer)


class FixedCost(Base):
    __tablename__ = "fixed_costs"
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount_positive"),
        CheckConstraint("day_of_month BETWEEN 1 AND 31", name="day_of_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    name: Mapped[str] = mapped_column(String(100))
    amount: Mapped[Decimal] = mapped_column(Money)
    day_of_month: Mapped[int] = mapped_column(Integer)


class LifeEvent(Base):
    __tablename__ = "life_events"
    __table_args__ = (
        enum_check("type", e.LifeEventType),
        enum_check("status", e.LifeEventStatus),
        CheckConstraint("est_cost >= 0", name="est_cost_not_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(user_fk(), index=True)
    name: Mapped[str] = mapped_column(String(200))
    date: Mapped[date] = mapped_column(Date)
    est_cost: Mapped[Decimal] = mapped_column(Money)
    type: Mapped[str] = mapped_column(String(20))
    source: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(10), default=e.LifeEventStatus.PLANNED)


class LifeProfile(Base):
    """Soft coaching notes only (arch 4.3 v0.8); facts live in life_facts."""

    __tablename__ = "life_profile"

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class PlanPreferences(Base):
    __tablename__ = "plan_preferences"
    __table_args__ = (CheckConstraint("buffer_pct BETWEEN 0 AND 0.3", name="buffer_pct"),)

    user_id: Mapped[int] = mapped_column(user_fk(), primary_key=True)
    weekday_weights: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    pinned_days: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    category_caps: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    buffer_pct: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=Decimal("0.10"))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class Product(Base):
    """Mock product catalogue (data/products.json); `id` is the file's slug."""

    __tablename__ = "products"
    __table_args__ = (
        enum_check("kind", e.ProductKind),
        enum_check("liquidity", e.Liquidity),
        CheckConstraint("min_months <= max_months", name="months_range"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    kind: Mapped[str] = mapped_column(String(20))
    rate: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    liquidity: Mapped[str] = mapped_column(String(10))
    description: Mapped[str | None] = mapped_column(Text)
    min_months: Mapped[int | None]
    max_months: Mapped[int | None]
    mock: Mapped[bool] = mapped_column(Boolean, default=True)


class SimClock(Base):
    """The demo's fake "now" (one row, id = 1)."""

    __tablename__ = "sim_clock"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1, autoincrement=False)
    today: Mapped[date] = mapped_column(Date)
