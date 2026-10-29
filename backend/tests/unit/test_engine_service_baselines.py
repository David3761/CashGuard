"""Shell `recompute_baselines(db, user_id)`: loads the context, calls the core, writes both results."""

import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("app.services.context_loader", reason="needs bomboe's services (B3/B4)")

from app.domain.enums import Category, FactType
from app.domain.models import HouseholdMemberValue

from app.engine import service
from tests.builders import fact, tx

TODAY = date(2026, 6, 15)
PRIORS = {
    "city_index": {"Cluj": 1.0},
    "categories": {"groceries": {"basket_median": 70, "monthly_median": 800, "cv": 0.25}},
}


class FakeServices:
    def __init__(self) -> None:
        self.saved: list[tuple[int, list[Any]]] = []
        self.scales: list[tuple[int, Decimal]] = []
        self.loaded: list[tuple[int, date]] = []

    async def load_user_context(self, db: Any, user_id: int, today: date) -> Any:
        self.loaded.append((user_id, today))
        kids = [HouseholdMemberValue(role="child", age=7), HouseholdMemberValue(role="child", age=11)]
        facts = [
            fact(type=FactType.HOUSEHOLD_MEMBER, value=v) for v in (HouseholdMemberValue(role="adult"), *kids)
        ]
        return SimpleNamespace(
            profile=SimpleNamespace(city="Cluj"),
            facts=facts,
            transactions=[tx(category=Category.GROCERIES, effective_amount=Decimal(140))],
        )

    async def replace_all(self, db: Any, user_id: int, baselines: list[Any]) -> None:
        self.saved.append((user_id, baselines))

    async def update_household_scale(self, db: Any, user_id: int, scale: Decimal) -> None:
        self.scales.append((user_id, scale))


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> FakeServices:
    f = FakeServices()
    monkeypatch.setattr("app.engine.service.load_user_context", f.load_user_context)
    monkeypatch.setattr("app.engine.service.baselines_service.replace_all", f.replace_all)
    monkeypatch.setattr("app.engine.service.users_service.update_household_scale", f.update_household_scale)
    monkeypatch.setattr("app.engine.service.clock.today", lambda: TODAY)
    monkeypatch.setattr("app.engine.service.load_priors", lambda: PRIORS)
    return f


def test_recompute_baselines_writes_baselines_and_household_scale(fakes: FakeServices) -> None:
    result = asyncio.run(service.recompute_baselines(db=None, user_id=7))
    assert fakes.loaded == [(7, TODAY)]
    assert fakes.scales == [(7, Decimal("2.1"))]
    ((user_id, saved),) = fakes.saved
    assert user_id == 7
    assert {b.category for b in saved} == {Category.GROCERIES}
    assert set(result) == {"groceries"}
    assert result["groceries"].household_multiplier == Decimal("2.1")


def test_recompute_baselines_is_idempotent(fakes: FakeServices) -> None:
    first = asyncio.run(service.recompute_baselines(db=None, user_id=7))
    second = asyncio.run(service.recompute_baselines(db=None, user_id=7))
    assert first == second
    assert fakes.saved[0] == fakes.saved[1]
    assert fakes.scales[0] == fakes.scales[1]
