"""Income-source and fixed-cost tool handlers (A3 step 3; arch 6.6)."""

from collections.abc import Mapping
from typing import Any

from app.agent.handlers.records import adder, check_day, check_money, remover, updater
from app.agent.ports import RecordsPort, Services


def _income(services: Services) -> RecordsPort:
    return services.income_sources


def _costs(services: Services) -> RecordsPort:
    return services.fixed_costs


def _check(data: Mapping[str, Any]) -> None:
    check_money(data, "amount")
    check_day(data)


_INCOME_IDS = ("income_source_id", "source_id", "id")
_COST_IDS = ("fixed_cost_id", "cost_id", "id")

add_income_source = adder(_income, "income_source", _check)
update_income_source = updater(_income, "income_source", _INCOME_IDS, _check)
remove_income_source = remover(_income, "income_source", _INCOME_IDS)
add_fixed_cost = adder(_costs, "fixed_cost", _check)
update_fixed_cost = updater(_costs, "fixed_cost", _COST_IDS, _check)
remove_fixed_cost = remover(_costs, "fixed_cost", _COST_IDS)
