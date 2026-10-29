"""Persona data generator (E12, arch 16.1 / 16.5).

Reads `data/personas/<id>/config.json` (inputs we write) and writes `profile.json` +
`transactions.json`
next to it: 4 months of history (2026-02-15 … 2026-06-14, Bucharest time) before the demo date. A
config can start earlier with `history_from` (Elena, the heavy persona: 4 years).
Deterministic: one seeded `random.Random` per persona, sorted JSON, so two runs give identical
bytes.
The start balance is computed backwards, so the history ends exactly on `current_balance`.

    python scripts/generate_personas.py            # every persona under data/personas/
    python scripts/generate_personas.py matei      # one persona
"""

import json
import math
import random
import sys
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

BUCHAREST = ZoneInfo("Europe/Bucharest")
HISTORY_FROM = date(2026, 2, 15)
HISTORY_TO = date(2026, 6, 14)
AS_OF = date(2026, 6, 15)
DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "personas"
CENT = Decimal("0.01")

# purpose of the seeded history, from the category (the answered ones are set by `answered` in the
# config)
PURPOSE_BY_CATEGORY = {
    "groceries": "essential_living",
    "transport": "essential_living",
    "fuel": "essential_living",
    "health_pharmacy": "essential_living",
    "housing_rent": "essential_living",
    "utilities": "essential_living",
    "telecom": "essential_living",
    "household_goods": "essential_living",
    "kids": "household_care",
    "pets": "household_care",
    "restaurants": "social_connection",
    "gifts": "social_connection",
    "entertainment": "identity_joy",
    "sport": "identity_joy",
    "subscriptions": "identity_joy",
    "education": "self_investment",
    "books": "self_investment",
    "food_delivery": "unplanned_discretionary",
    "clothing": "unplanned_discretionary",
    "electronics": "unplanned_discretionary",
    "personal_care": "essential_living",
    "travel": "identity_joy",
    "other": "unknown",
}


def money(x: float | Decimal | str) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_HALF_UP)


def clamp_day(year: int, month: int, day: int) -> date:
    last = (date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day, last))


def history_days(start: date = HISTORY_FROM) -> list[date]:
    return [start + timedelta(days=i) for i in range((HISTORY_TO - start).days + 1)]


def history_months(start: date = HISTORY_FROM) -> list[tuple[int, int]]:
    """(year, month) of every month the history window touches."""
    first, last = start.year * 12 + start.month - 1, HISTORY_TO.year * 12 + HISTORY_TO.month - 1
    return [(i // 12, i % 12 + 1) for i in range(first, last + 1)]


def month_days(day_of_month: int, start: date = HISTORY_FROM) -> list[date]:
    """The date `day_of_month` falls on in every month of the history window."""
    out = []
    for year, month in history_months(start):
        d = clamp_day(year, month, day_of_month)
        if start <= d <= HISTORY_TO:
            out.append(d)
    return out


class Generator:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.rng = random.Random(config["seed"])  # noqa: S311 (seeded test data, not crypto)
        self.start = date.fromisoformat(config.get("history_from", HISTORY_FROM.isoformat()))
        self.rows: list[dict[str, Any]] = []

    # ── helpers ──────────────────────────────────────────────────────────────

    def at(self, d: date, hours: list[int]) -> datetime:
        start, end = hours
        minute = self.rng.randrange((end - start) * 60) if end > start else 0
        return datetime.combine(d, time(start), tzinfo=BUCHAREST) + timedelta(minutes=minute)

    def amount(self, stream: dict[str, Any], multiplier: float = 1.0) -> Decimal:
        if "range" in stream:
            low, high = stream["range"]
            value = self.rng.uniform(low, high)
        elif "median" in stream:
            value = stream["median"] * math.exp(self.rng.gauss(0.0, stream.get("sigma", 0.3)))
            value = min(max(value, stream.get("min", 1)), stream.get("max", 10 * stream["median"]))
        else:
            value = float(stream["amount"])
        return money(value * multiplier)

    def add(
        self, when: datetime, amount: Decimal, stream: dict[str, Any], direction: str = "debit"
    ) -> None:
        merchant = stream["merchant_raw"]
        if isinstance(merchant, list):
            merchant = self.rng.choice(merchant)
        self.rows.append(
            {
                "occurred_at": when,
                "amount": amount,
                "direction": direction,
                "merchant_raw": merchant,
                "mcc": stream.get("mcc"),
                "category": stream["category"],
                "description": stream.get("description"),
                "stream": stream["name"],
            }
        )

    def multiplier(self, stream: dict[str, Any], d: date) -> float:
        for spike in self.config.get("spikes", []):
            if spike["stream"] == stream["name"] and date.fromisoformat(
                spike["from"]
            ) <= d <= date.fromisoformat(spike["to"]):
                return float(spike["multiplier"])
        return 1.0

    def quiet(self, d: date, stream: dict[str, Any]) -> bool:
        """Days a stream pauses (a week at home, a trip…): `quiet` periods list the streams they
        pause."""
        return any(
            stream["name"] in q["streams"]
            and date.fromisoformat(q["from"]) <= d <= date.fromisoformat(q["to"])
            for q in self.config.get("quiet", [])
        )

    # ── streams ──────────────────────────────────────────────────────────────

    def recurring(self) -> None:
        for income in self.config["income_sources"]:
            stream = {"name": "salary", "category": "income", **income}
            for d in month_days(income["day_of_month"], self.start):
                self.add(self.at(d, [8, 9]), money(income["amount"]), stream, "credit")
        for cost in self.config["fixed_costs"]:
            stream = {**cost, "name": f"fixed:{cost['name']}"}
            jitter = cost.get("jitter_pct", 0)
            for d in month_days(cost["day_of_month"], self.start):
                factor = 1 + self.rng.uniform(-jitter, jitter) / 100 if jitter else 1
                self.add(
                    self.at(d, [9, 11]),
                    money(Decimal(str(cost["amount"])) * Decimal(str(factor))),
                    stream,
                )

    def irregular_income(self) -> None:
        spec = self.config.get("irregular_income")
        if not spec:
            return
        for monday in [d for d in history_days(self.start) if d.weekday() == 0]:
            d = monday + timedelta(days=self.rng.randrange(7))
            if d <= HISTORY_TO:
                self.add(
                    self.at(d, [20, 23]),
                    self.amount(spec["tips"]),
                    {"name": "tips", **spec["tips"]},
                    "credit",
                )
        for year, month in history_months(self.start):
            day = self.rng.randint(*spec["wage"]["days"])
            d = clamp_day(year, month, day)
            if self.start <= d <= HISTORY_TO:
                self.add(
                    self.at(d, [9, 12]),
                    self.amount(spec["wage"]),
                    {"name": "wage", **spec["wage"]},
                    "credit",
                )

    def weekly(self, stream: dict[str, Any]) -> None:
        weekdays = stream.get("weekdays", [1, 2, 3, 4, 5, 6, 7])
        for monday in [d for d in history_days(self.start) if d.weekday() == 0] + [
            self.start - timedelta(self.start.weekday())
        ]:
            low, high = stream["per_week"]
            count = self.rng.randint(low, high)
            days = sorted(self.rng.sample(weekdays, min(count, len(weekdays))))
            for wd in days:
                d = monday + timedelta(days=wd - 1)
                if self.start <= d <= HISTORY_TO and not self.quiet(d, stream):
                    self.add(
                        self.at(d, stream["hours"]),
                        self.amount(stream, self.multiplier(stream, d)),
                        stream,
                    )

    def every(self, stream: dict[str, Any]) -> None:
        for d in history_days(self.start):
            due = d.isoweekday() in stream["weekdays"] and not self.quiet(d, stream)
            if due and self.rng.random() < stream.get("probability", 1.0):
                self.add(
                    self.at(d, stream["hours"]),
                    self.amount(stream, self.multiplier(stream, d)),
                    stream,
                )

    def monthly(self, stream: dict[str, Any]) -> None:
        for d in month_days(stream["day_of_month"], self.start):
            self.add(self.at(d, stream.get("hours", [10, 18])), self.amount(stream), stream)

    def calendar(self) -> None:
        for event in self.config.get("calendar", []):
            d = date.fromisoformat(event["date"])
            self.add(
                self.at(d, event.get("hours", [10, 19])),
                money(event["amount"]),
                {"name": "calendar", **event},
            )

    # ── finishing ────────────────────────────────────────────────────────────

    def items(self, row: dict[str, Any]) -> list[dict[str, Any]] | None:
        catalogue = self.config.get("receipt_items", {}).get(row["stream"])
        if not catalogue or self.rng.random() >= self.config.get("receipt_share", 0.2):
            return None
        names = self.rng.sample(catalogue, min(len(catalogue), self.rng.randint(2, 4)))
        weights = [self.rng.uniform(1, 3) for _ in names]
        total = row["amount"]
        parts = [money(total * Decimal(str(w / sum(weights)))) for w in weights]
        parts[-1] = total - sum(parts[:-1], Decimal(0))
        return [{"name": n, "qty": 1, "amount": str(p)} for n, p in zip(names, parts, strict=False)]

    def annotate(self, rows: list[dict[str, Any]]) -> None:
        for row in rows:
            row["items"] = self.items(row) if row["direction"] == "debit" else None
            row["annotation"] = (
                {
                    "purpose": PURPOSE_BY_CATEGORY.get(row["category"], "unknown"),
                    "beneficiary": "self",
                    "effective_amount": str(row["amount"]),
                    "source": "auto",
                    "label": None,
                }
                if row["direction"] == "debit"
                else None
            )
        for answered in self.config.get("answered", []):
            matching = [r for r in rows if r["stream"] == answered["stream"]]
            for row in matching[-answered["last"] :]:
                row["annotation"].update(
                    {"purpose": answered["purpose"], "source": "answer", "label": answered["label"]}
                )

    def run(self) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        self.recurring()
        self.irregular_income()
        for stream in self.config.get("streams", []):
            getattr(self, stream["kind"])(stream)
        self.calendar()
        rows = sorted(self.rows, key=lambda r: (r["occurred_at"], r["merchant_raw"], r["amount"]))
        self.annotate(rows)
        pid = self.config["id"]
        transactions = [
            {
                "ref": f"{pid}-{i:04d}",
                **{k: v for k, v in row.items() if k != "occurred_at"},
                "occurred_at": row["occurred_at"].isoformat(),
                "amount": str(row["amount"]),
            }
            for i, row in enumerate(rows, 1)
        ]
        net = sum(
            (r["amount"] if r["direction"] == "credit" else -r["amount"] for r in rows), Decimal(0)
        )
        current = money(self.config["current_balance"])
        return self.profile(current, current - net), transactions

    def profile(self, current: Decimal, start: Decimal) -> dict[str, Any]:
        c = self.config
        return {
            "id": c["id"],
            "user": c["user"],
            "account": {"current_balance": str(current)},
            "income_sources": [
                {k: v for k, v in s.items() if k in ("source", "amount", "day_of_month")}
                for s in c["income_sources"]
            ],
            "fixed_costs": [
                {k: v for k, v in f.items() if k in ("name", "amount", "day_of_month")}
                for f in c["fixed_costs"]
            ],
            "goal": c.get("goal"),
            "goal_pot": c.get("goal_pot"),
            "pots": c.get("pots", []),
            "plan_preferences": c.get("plan_preferences", {}),
            "history": {
                "from": self.start.isoformat(),
                "to": HISTORY_TO.isoformat(),
                "as_of": AS_OF.isoformat(),
                "start_balance": str(start),
            },
        }


def generate(config: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return Generator(config).run()


def dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n"


def write_persona(folder: Path) -> None:
    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    profile, transactions = generate(config)
    (folder / "profile.json").write_text(dump(profile), encoding="utf-8")
    (folder / "transactions.json").write_text(dump(transactions), encoding="utf-8")


def main(argv: list[str]) -> None:
    folders = (
        [DATA_DIR / name for name in argv]
        if argv
        else sorted(p for p in DATA_DIR.iterdir() if p.is_dir())
    )
    for folder in folders:
        write_persona(folder)
        print(f"wrote {folder.relative_to(DATA_DIR.parents[1])}")


if __name__ == "__main__":
    main(sys.argv[1:])
