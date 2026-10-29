"""Scenario files (data/scenarios/<id>.json, D2) and optional scripted days
(data/sim_days/<YYYY-MM-DD>.json: a list of {persona, merchant_raw, amount, …, time})."""

import json
import re
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from app.clock import BUCHAREST
from app.db.seed import DATA_DIR
from app.errors import DomainError

_SLUG = re.compile(r"^[a-z0-9_]{1,64}$")


def load(scenario_id: str, data_dir: Path = DATA_DIR) -> dict[str, Any]:
    path = data_dir / "scenarios" / f"{scenario_id}.json"
    if not _SLUG.match(scenario_id) or not path.exists():
        raise DomainError("scenario_not_found", f"No scenario {scenario_id!r}.", status=404)
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def occurred_at(today: date, entry: dict[str, Any]) -> datetime:
    """`day_offset` days from the sim date at `time` (HH:MM, Bucharest)."""
    day = today + timedelta(days=int(entry.get("day_offset", 0)))
    return datetime.combine(day, time.fromisoformat(entry.get("time", "12:00")), tzinfo=BUCHAREST)


def scripted_day(day: date, data_dir: Path = DATA_DIR) -> list[dict[str, Any]]:
    path = data_dir / "sim_days" / f"{day.isoformat()}.json"
    rows: list[dict[str, Any]] = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    )
    return rows
