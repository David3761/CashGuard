"""Test builders: small, valid domain objects and four hand-made persona contexts (F2 step 8).

Every builder goes through `model_validate`, so an override is validated, never bypassed, and a
test can pass plain values (`tx(amount="500")`). No clock: fixed dates around the demo start,
2026-06-15, a Monday (D35). The persona numbers follow arch 16.1, but they're unit-test fixtures,
not the seeded data (that's danutu's E12).
"""

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.domain.enums import FactType
from app.domain.models import LifeFact, PatternRule, Signature, TxView
from app.domain.user_context import UserContext

TODAY = date(2026, 6, 15)
BUCHAREST = ZoneInfo("Europe/Bucharest")


def returning(value: Any) -> Any:
    """An async stand-in for one of bomboe's loaders (B3/B4 are async): always `value`."""

    async def load(*args: Any) -> Any:
        return value

    return load


def at(day: date, hour: int = 12, minute: int = 0) -> datetime:
    """An aware Bucharest timestamp."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=BUCHAREST)


CREATED = at(date(2026, 3, 1), 9)

DEFAULT_VALUES: dict[FactType, dict[str, Any]] = {
    FactType.OCCUPATION: {"title": "junior developer", "work_mode": "office Tue-Thu"},
    FactType.EMPLOYMENT: {"kind": "employee"},
    FactType.INCOME_PATTERN: {"irregular": False},
    FactType.HOUSEHOLD_MEMBER: {"role": "adult", "relation": "partner"},
    FactType.PET: {"species": "cat"},
    FactType.HOUSING: {"kind": "rent"},
    FactType.CITY: {"name": "București"},
    FactType.VEHICLE: {"kind": "car"},
    FactType.COMMUTE: {"mode": "public_transport"},
    FactType.ACTIVITY: {"name": "running", "per_week": 3},
    FactType.SOCIAL_PATTERN: {"name": "team lunch", "weekdays": [5]},
    FactType.LIFE_EVENT: {"name": "Vacanță la mare", "months": [8]},
    FactType.RHYTHM: {"name": "work shifts", "weekdays": [2, 4]},
    FactType.PRIORITY: {"category": "concerts", "priority": "protected"},
    FactType.CUSTOM: {"description": "fac cosplay"},
}


def tx(**overrides: Any) -> TxView:
    """A resolved Mega Image lunch basket of 85 lei (Matei's usual)."""
    return TxView.model_validate(
        {
            "id": 1,
            "occurred_at": at(TODAY, 13, 5),
            "merchant_raw": "MEGA IMAGE 0451 BUCURESTI",
            "merchant": "Mega Image",
            "merchant_id": "mega_image",
            "mcc": "5411",
            "category": "groceries",
            "direction": "debit",
            "amount": "85.00",
            "effective_amount": "85.00",
            "purpose": "essential_living",
            "beneficiary": "self",
            "annotation_source": "auto",
            "annotation_confidence": 0.8,
            "decision": "auto",
            **overrides,
        }
    )


def fact(type: FactType = FactType.OCCUPATION, **overrides: Any) -> LifeFact:
    """A confirmed, permanent fact with a valid value for its type."""
    return LifeFact.model_validate(
        {
            "id": 1,
            "type": type,
            "value": DEFAULT_VALUES[type],
            "text": "Sunt developer junior",
            "source": "seed",
            "status": "confirmed",
            "confidence": 0.95,
            "persistence": "permanent",
            "valid_from": date(2026, 1, 1),
            "created_at": CREATED,
            **overrides,
        }
    )


def signature(**overrides: Any) -> Signature:
    """Andrei's TV signature (arch 5.3.3): a TV is a work tool for a sports analyst."""
    return Signature.model_validate(
        {
            "fact_id": 1,
            "effect": "explains",
            "category": "electronics",
            "merchant_hints": ["eMAG", "Altex", "Flanco"],
            "item_keywords": ["televizor", "TV", "monitor", "soundbar"],
            "amount_min": "1500",
            "amount_max": "9000",
            "replacement_cycle_days": 900,
            "purpose": "work_tool",
            "strength": 0.9,
            "origin": "library",
            **overrides,
        }
    )


def rule(**overrides: Any) -> PatternRule:
    """Matei's Friday team lunch (D1): restaurants, Fri 12:00-15:00, 60-130 lei, at 0.7."""
    return PatternRule.model_validate(
        {
            "id": 1,
            "kind": "classify",
            "match": {
                "category": "restaurants",
                "weekdays": [5],
                "from": "12:00",
                "to": "15:00",
                "amount_min": "60",
                "amount_max": "130",
            },
            "outcome": {"purpose": "social_connection", "label": "Prânz cu echipa"},
            "confidence": 0.7,
            "hits": 2,
            "source": "learned",
            "created_at": CREATED,
            **overrides,
        }
    )


def ctx(**overrides: Any) -> UserContext:
    """A fresh user (like Alex): a profile and an account, nothing else."""
    return UserContext.model_validate(
        {
            "user_id": 5,
            "as_of": TODAY,
            "profile": {"name": "Alex", "language": "ro", "coach_style": "warm"},
            "account": {"current_balance": "1200", "savings_pot": "0"},
            **overrides,
        }
    )


def _goal(goal_id: int, amount: str, deadline: date, saved: str) -> dict[str, Any]:
    return {
        "goal": {
            "id": goal_id,
            "amount": amount,
            "deadline": deadline,
            "status": "active",
            "created_at": CREATED,
        },
        "goal_pot": {
            "id": goal_id,
            "name": "Obiectiv",
            "kind": "goal",
            "goal_id": goal_id,
            "target": amount,
            "saved": saved,
            "status": "active",
        },
    }


def _fact(fact_id: int, type: FactType, value: dict[str, Any], text: str) -> dict[str, Any]:
    return fact(type, id=fact_id, value=value, text=text).model_dump()


def _baseline(category: str, median: str, multiplier: str = "1") -> dict[str, Any]:
    return {
        "category": category,
        "personal_median": median,
        "personal_mad": "20",
        "n": 40,
        "prior_median": median,
        "household_multiplier": multiplier,
        "expected_median": median,
        "monthly_expected": str(int(median) * 12),
    }


def matei_ctx() -> UserContext:
    """Matei, 26, junior developer in București, lives alone (16.1; Scenes A, C, D)."""
    lunches = [
        tx(id=i, occurred_at=at(date(2026, 6, day), 13, 5), amount=amount, effective_amount=amount)
        for i, (day, amount) in enumerate([(8, "82"), (9, "88"), (10, "85"), (11, "79")], start=10)
    ]
    friday_lunches = [
        tx(
            id=20 + i,
            occurred_at=at(day, 13, 10),
            merchant_raw="TRATTORIA BUONGUSTO",
            merchant=None,
            merchant_id=None,
            mcc="5812",
            category="restaurants",
            amount="95",
            effective_amount="95",
            purpose="social_connection",
            annotation_source="answer",
        )
        for i, day in enumerate([date(2026, 5, 29), date(2026, 6, 5)])
    ]
    return ctx(
        user_id=1,
        profile={
            "name": "Matei",
            "age": 26,
            "language": "ro",
            "coach_style": "warm",
            "city": "București",
        },
        account={"current_balance": "6400", "savings_pot": "5200"},
        **_goal(1, "10000", date(2026, 12, 31), "5200"),
        income_sources=[{"id": 1, "source": "Salariu", "amount": "7000", "day_of_month": 10}],
        fixed_costs=[
            {"id": 1, "name": "Chirie", "amount": "2000", "day_of_month": 1},
            {"id": 2, "name": "Utilități", "amount": "350", "day_of_month": 15},
            {"id": 3, "name": "Telefon", "amount": "60", "day_of_month": 20},
            {"id": 4, "name": "Spotify", "amount": "25", "day_of_month": 5},
            {"id": 5, "name": "Sală", "amount": "180", "day_of_month": 1},
        ],
        facts=[
            _fact(1, FactType.OCCUPATION, DEFAULT_VALUES[FactType.OCCUPATION], "Sunt developer"),
            _fact(2, FactType.HOUSING, {"kind": "rent", "note": "lives alone"}, "Stau singur"),
            _fact(3, FactType.CITY, {"name": "București"}, "Stau în București"),
            _fact(4, FactType.PRIORITY, DEFAULT_VALUES[FactType.PRIORITY], "Concertele contează"),
            _fact(
                5,
                FactType.PRIORITY,
                {"category": "food_delivery", "priority": "reduce"},
                "Vreau să comand mai rar",
            ),
        ],
        signatures=[
            signature(
                fact_id=4,
                effect="protects",
                category="entertainment",
                merchant_hints=["iaBilet", "Eventim"],
                item_keywords=["concert"],
                amount_min=None,
                amount_max=None,
                replacement_cycle_days=None,
                purpose="identity_joy",
            ),
        ],
        rules=[rule()],
        baselines={"groceries": _baseline("groceries", "85")},
        transactions=lunches + friday_lunches,
    )


def andrei_ctx() -> UserContext:
    """Andrei, 31, sports analyst working from home, lives with his partner (16.1; Scene B)."""
    return ctx(
        user_id=2,
        profile={
            "name": "Andrei",
            "age": 31,
            "language": "ro",
            "coach_style": "direct",
            "household_scale": "1.5",
            "city": "București",
        },
        account={"current_balance": "8200", "savings_pot": "4000"},
        **_goal(2, "15000", date(2027, 3, 31), "4000"),
        income_sources=[{"id": 2, "source": "Salariu", "amount": "9000", "day_of_month": 5}],
        fixed_costs=[{"id": 6, "name": "Chirie", "amount": "2600", "day_of_month": 1}],
        facts=[
            _fact(
                11,
                FactType.OCCUPATION,
                {"title": "analist sportiv", "work_mode": "remote"},
                "Sunt analist sportiv, lucrez de acasă",
            ),
            _fact(
                12,
                FactType.HOUSEHOLD_MEMBER,
                {"role": "adult", "relation": "partner"},
                "Stau cu prietena mea",
            ),
        ],
        signatures=[
            signature(fact_id=11),
            signature(
                fact_id=11,
                category="subscriptions",
                merchant_hints=["Digi Sport", "Prima Sport", "DAZN", "Voyo"],
                item_keywords=[],
                amount_min=None,
                amount_max=None,
                replacement_cycle_days=None,
            ),
        ],
    )


def bianca_ctx() -> UserContext:
    """Bianca, 22, student and part-time barista in Iași, shares a flat (16.1; Scene B)."""
    return ctx(
        user_id=3,
        profile={
            "name": "Bianca",
            "age": 22,
            "language": "ro",
            "coach_style": "warm",
            "city": "Iași",
        },
        account={"current_balance": "1900", "savings_pot": "900"},
        **_goal(3, "3000", date(2026, 8, 31), "900"),
        income_sources=[
            {"id": 3, "source": "Barista (cu bacșiș)", "amount": "2800", "day_of_month": 1}
        ],
        fixed_costs=[{"id": 7, "name": "Chirie (partea mea)", "amount": "700", "day_of_month": 1}],
        facts=[
            _fact(
                21,
                FactType.OCCUPATION,
                {"title": "barista", "work_mode": "part_time"},
                "Sunt barista",
            ),
            _fact(22, FactType.EMPLOYMENT, {"kind": "student"}, "Sunt studentă"),
            _fact(
                23, FactType.INCOME_PATTERN, {"irregular": True, "note": "tips"}, "Venitul variază"
            ),
            _fact(24, FactType.HOUSING, {"kind": "shared_flat"}, "Stau cu o colegă"),
            _fact(25, FactType.CITY, {"name": "Iași"}, "Stau în Iași"),
        ],
    )


def ioana_ctx() -> UserContext:
    """Ioana, 38, accountant in Cluj; partner and children aged 7 and 11, scale 2.1 (16.1; E)."""
    return ctx(
        user_id=4,
        profile={
            "name": "Ioana",
            "age": 38,
            "language": "ro",
            "coach_style": "warm",
            "household_scale": "2.1",
            "city": "Cluj",
        },
        account={"current_balance": "21000", "savings_pot": "6000"},
        **_goal(4, "12000", date(2026, 12, 31), "6000"),
        income_sources=[
            {"id": 4, "source": "Venit gospodărie", "amount": "15500", "day_of_month": 10}
        ],
        fixed_costs=[{"id": 8, "name": "Rată casă", "amount": "3200", "day_of_month": 10}],
        facts=[
            _fact(31, FactType.OCCUPATION, {"title": "contabilă"}, "Sunt contabilă"),
            _fact(
                32, FactType.HOUSEHOLD_MEMBER, {"role": "adult", "relation": "partner"}, "Soțul meu"
            ),
            _fact(33, FactType.HOUSEHOLD_MEMBER, {"role": "child", "age": 7}, "Fiica mea, 7 ani"),
            _fact(34, FactType.HOUSEHOLD_MEMBER, {"role": "child", "age": 11}, "Fiul meu, 11 ani"),
            _fact(35, FactType.CITY, {"name": "Cluj"}, "Stăm în Cluj"),
        ],
        signatures=[
            signature(
                fact_id=33,
                effect="expects_event",
                category="books",
                merchant_hints=[],
                item_keywords=["rechizite"],
                amount_min=None,
                amount_max=None,
                replacement_cycle_days=None,
                time_window={"months": [8, 9]},
                expected_amount="600",
                purpose="household_care",
                strength=0.8,
            ),
        ],
        baselines={"groceries": _baseline("groceries", "140", "2.1")},
    )
