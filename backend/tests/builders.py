"""Domain objects for unit tests (F2): small builders with sensible defaults + the 4 personas.

The personas are small and hand-made (arch 16.1). The big seeded data comes from danutu's
generator (E12); don't tune demo numbers here.
"""

from datetime import date, datetime, time
from decimal import Decimal
from itertools import count
from typing import Any
from zoneinfo import ZoneInfo

from app.domain import models as dm
from app.domain.enums import (
    AnnotationSource,
    Category,
    Purpose,
    TransactionStatus,
)

TODAY = date(2026, 6, 15)  # Monday, the demo start (D35)
BUCHAREST = ZoneInfo("Europe/Bucharest")
D = Decimal
_ids = count(1000)


def at(day: date, hh: int = 12, mm: int = 0) -> datetime:
    """A Bucharest wall-clock time as an aware datetime."""
    return datetime.combine(day, time(hh, mm), tzinfo=BUCHAREST)


# ── small builders ───────────────────────────────────────────────────────────────────────


def tx(**kw: Any) -> dm.TxView:
    base: dict[str, Any] = {
        "id": next(_ids),
        "amount": D("85"),
        "occurred_at": at(TODAY, 13, 5),
        "merchant_raw": "MEGA IMAGE 0451 BUCURESTI",
        "merchant_id": "mega_image",
        "merchant": "Mega Image",
        "category": Category.GROCERIES,
    }
    return dm.TxView(**(base | kw))


def history(**kw: Any) -> dm.TxView:
    """A past, resolved transaction (what `UserContext.transactions` holds)."""
    base: dict[str, Any] = {
        "status": TransactionStatus.RESOLVED,
        "annotation_source": AnnotationSource.AUTO,
        "purpose": Purpose.ESSENTIAL_LIVING,
    }
    return tx(**(base | kw))


def fact(**kw: Any) -> dm.LifeFact:
    base: dict[str, Any] = {
        "id": next(_ids),
        "type": "occupation",
        "value": {"title": "junior developer"},
        "source": "seed",
    }
    return dm.LifeFact(**(base | kw))


def signature(**kw: Any) -> dm.Signature:
    base: dict[str, Any] = {
        "id": next(_ids),
        "effect": "explains",
        "category": Category.ELECTRONICS,
        "purpose": Purpose.WORK_TOOL,
        "strength": 0.9,
    }
    return dm.Signature(**(base | kw))


def rule(**kw: Any) -> dm.PatternRule:
    """Default: Matei's Friday team lunch (arch 16.1), learned twice → 0.7."""
    base: dict[str, Any] = {
        "id": next(_ids),
        "kind": "classify",
        "source": "answer",
        "confidence": 0.7,
        "hits": 2,
        "match": {
            "category": "restaurants",
            "weekdays": [5],
            "from": "12:00",
            "to": "15:00",
            "amount_min": 60,
            "amount_max": 130,
        },
        "outcome": {"purpose": "social_connection", "label": "Prânz cu echipa"},
    }
    return dm.PatternRule(**(base | kw))


def ctx(**kw: Any) -> dm.UserContext:
    base: dict[str, Any] = {
        "today": TODAY,
        "profile": dm.UserProfile(id=1, name="Test"),
        "account": dm.Account(current_balance=D("1000")),
    }
    return dm.UserContext(**(base | kw))


def _goal(
    user_goal_id: int,
    amount: str,
    deadline: date,
    motivation: str,
    soft: bool = True,
    saved: str = "0",
) -> tuple[dm.Goal, dm.Pot]:
    goal = dm.Goal(
        id=user_goal_id, amount=D(amount), deadline=deadline, motivation=motivation, soft=soft
    )
    pot = dm.Pot(
        id=user_goal_id,
        name=motivation,
        kind="goal",
        goal_id=goal.id,
        target=goal.amount,
        saved=D(saved),
    )
    return goal, pot


def _baseline(
    category: Category, median: str, mad: str, n: int, monthly: str, multiplier: str = "1"
) -> dm.Baseline:
    return dm.Baseline(
        category=category,
        personal_median=D(median),
        personal_mad=D(mad),
        n=n,
        expected_median=D(median),
        monthly_expected=D(monthly),
        household_multiplier=D(multiplier),
    )


# ── personas (arch 16.1) ─────────────────────────────────────────────────────────────────


def matei_ctx(**kw: Any) -> dm.UserContext:
    """26, junior developer, lives alone in București; protects concerts, wants less delivery."""
    goal, goal_pot = _goal(1, "10000", date(2026, 12, 31), "Fond 10.000", saved="5200")
    job = fact(
        type="occupation",
        value={"title": "junior developer", "work_mode": "hybrid"},
        text="Sunt junior developer, la birou marți–joi",
    )
    facts = (
        job,
        fact(type="housing", value={"kind": "rent", "lives_alone": True}, text="Stau singur"),
        fact(
            type="priority",
            value={"category": "entertainment", "label": "concerte", "priority": "protected"},
            text="Concertele nu le tai",
        ),
        fact(
            type="priority",
            value={"category": "food_delivery", "priority": "reduce"},
            text="Aș vrea să comand mai rar",
        ),
    )
    lunches = tuple(
        history(
            amount=D(a),
            merchant_raw="TRATTORIA",
            merchant=None,
            merchant_id=None,
            category=Category.RESTAURANTS,
            occurred_at=at(day, 13, 10),
            purpose=Purpose.SOCIAL_CONNECTION,
            annotation_source=AnnotationSource.ANSWER,
            explanation="Prânz cu echipa",
        )
        for a, day in (("95", date(2026, 6, 5)), ("88", date(2026, 6, 12)))
    )
    groceries = tuple(
        history(amount=D(a), occurred_at=at(day, 12, 40))
        for a, day in (
            ("82", date(2026, 6, 8)),
            ("91", date(2026, 6, 10)),
            ("79", date(2026, 6, 11)),
        )
    )
    base: dict[str, Any] = {
        "profile": dm.UserProfile(id=1, name="Matei", age=26, city="București"),
        "account": dm.Account(current_balance=D("2850"), savings_pot=goal_pot.saved),
        "goal": goal,
        "goal_pot": goal_pot,
        "income_sources": (
            dm.IncomeSource(id=1, source="Salariu", amount=D("7000"), day_of_month=10),
        ),
        "fixed_costs": (
            dm.FixedCost(id=1, name="Chirie", amount=D("2000"), day_of_month=1),
            dm.FixedCost(id=2, name="Utilități", amount=D("350"), day_of_month=15),
            dm.FixedCost(id=3, name="Telefon", amount=D("60"), day_of_month=20),
            dm.FixedCost(id=4, name="Spotify", amount=D("25"), day_of_month=5),
            dm.FixedCost(id=5, name="Sală", amount=D("180"), day_of_month=3),
        ),
        "pots": (goal_pot,),
        "facts": facts,
        "rules": (rule(),),
        "baselines": {
            Category.GROCERIES: _baseline(Category.GROCERIES, "85", "25", 48, "1150"),
            Category.RESTAURANTS: _baseline(Category.RESTAURANTS, "90", "15", 16, "380"),
            Category.FOOD_DELIVERY: _baseline(Category.FOOD_DELIVERY, "60", "12", 32, "480"),
        },
        "transactions": lunches + groceries,
    }
    return ctx(**(base | kw))


def andrei_ctx(**kw: Any) -> dm.UserContext:
    """31, sports analyst working from home, lives with his partner (scale 1.5)."""
    goal, goal_pot = _goal(2, "15000", date(2027, 3, 31), "Avans apartament", saved="6100")
    job = fact(
        type="occupation",
        value={"title": "analist sportiv", "work_mode": "remote"},
        text="Sunt analist sportiv, lucrez de acasă",
    )
    partner = fact(
        type="household_member",
        value={"role": "adult", "relation": "partener"},
        text="Stau cu partenera mea",
    )
    base: dict[str, Any] = {
        "profile": dm.UserProfile(
            id=2, name="Andrei", age=31, city="București", household_scale=D("1.5")
        ),
        "account": dm.Account(current_balance=D("6400"), savings_pot=goal_pot.saved),
        "goal": goal,
        "goal_pot": goal_pot,
        "income_sources": (
            dm.IncomeSource(id=2, source="Salariu", amount=D("9000"), day_of_month=5),
        ),
        "fixed_costs": (dm.FixedCost(id=6, name="Chirie", amount=D("2600"), day_of_month=1),),
        "pots": (goal_pot,),
        "facts": (job, partner),
        "signatures": (
            signature(
                fact_id=job.id,
                merchant_hints=("eMAG", "Altex", "Flanco"),
                item_keywords=("televizor", "TV", "monitor", "soundbar"),
                amount_min=D("1500"),
                amount_max=D("9000"),
                replacement_cycle_days=900,
            ),
            signature(
                fact_id=job.id,
                category=Category.SUBSCRIPTIONS,
                merchant_hints=("Digi Sport", "Prima Sport", "DAZN", "Voyo"),
            ),
        ),
        "baselines": {
            Category.GROCERIES: _baseline(Category.GROCERIES, "120", "30", 40, "1500", "1.5"),
        },
        "transactions": (history(amount=D("118"), occurred_at=at(date(2026, 6, 13), 18, 20)),),
    }
    return ctx(**(base | kw))


def bianca_ctx(**kw: Any) -> dm.UserContext:
    """22, student + part-time barista in Iași, shared flat, irregular income."""
    goal, goal_pot = _goal(3, "3000", date(2026, 8, 31), "Vara la mare", soft=False, saved="900")
    base: dict[str, Any] = {
        "profile": dm.UserProfile(id=3, name="Bianca", age=22, city="Iași"),
        "account": dm.Account(current_balance=D("740"), savings_pot=goal_pot.saved),
        "goal": goal,
        "goal_pot": goal_pot,
        "income_sources": (
            dm.IncomeSource(id=3, source="Barista", amount=D("2800"), day_of_month=15),
        ),
        "fixed_costs": (
            dm.FixedCost(id=7, name="Chirie (partea mea)", amount=D("700"), day_of_month=1),
        ),
        "pots": (goal_pot,),
        "facts": (
            fact(type="occupation", value={"title": "studentă"}, text="Sunt studentă"),
            fact(
                type="employment",
                value={"job": "barista", "part_time": True},
                text="Lucrez part-time ca barista",
            ),
            fact(
                type="income_pattern",
                value={"irregular": True, "tips": True},
                text="Câștig din bacșiș, variază",
            ),
            fact(type="housing", value={"kind": "shared_flat"}, text="Stau cu o colegă"),
        ),
        "baselines": {
            Category.GROCERIES: _baseline(Category.GROCERIES, "45", "15", 30, "520"),
        },
        "transactions": (
            history(
                amount=D("38"),
                merchant_raw="PROFI 112 IASI",
                merchant="Profi",
                merchant_id="profi",
                occurred_at=at(date(2026, 6, 14), 17, 45),
            ),
        ),
    }
    return ctx(**(base | kw))


def ioana_ctx(**kw: Any) -> dm.UserContext:
    """38, accountant in Cluj, partner + 2 children (7, 11) → household scale 2.1."""
    goal, goal_pot = _goal(4, "12000", date(2026, 12, 31), "Fond de urgență", saved="4300")
    household = fact(
        type="household_member",
        value={"role": "adult", "relation": "partener"},
        text="Suntem 4 acasă",
    )
    base: dict[str, Any] = {
        "profile": dm.UserProfile(
            id=4, name="Ioana", age=38, city="Cluj-Napoca", household_scale=D("2.1")
        ),
        "account": dm.Account(current_balance=D("9800"), savings_pot=goal_pot.saved),
        "goal": goal,
        "goal_pot": goal_pot,
        "income_sources": (
            dm.IncomeSource(id=4, source="Venit gospodărie", amount=D("15500"), day_of_month=10),
        ),
        "fixed_costs": (dm.FixedCost(id=8, name="Rată credit", amount=D("3200"), day_of_month=15),),
        "pots": (goal_pot,),
        "facts": (
            fact(type="occupation", value={"title": "contabilă"}, text="Sunt contabilă"),
            household,
            fact(type="household_member", value={"role": "child", "age": 7}, text="Fiica, 7 ani"),
            fact(type="household_member", value={"role": "child", "age": 11}, text="Fiul, 11 ani"),
        ),
        "signatures": (
            signature(
                fact_id=household.id,
                effect="scales_baseline",
                category=Category.GROCERIES,
                multiplier=D("2.1"),
                purpose=Purpose.HOUSEHOLD_CARE,
                strength=1.0,
            ),
            signature(
                fact_id=household.id,
                effect="expects_event",
                category=Category.BOOKS,
                expected_amount=D("600"),
                time_window={"months": [8, 9]},
                purpose=Purpose.HOUSEHOLD_CARE,
                strength=0.8,
            ),
        ),
        "baselines": {
            Category.GROCERIES: _baseline(Category.GROCERIES, "140", "35", 70, "3600", "2.1"),
        },
        "transactions": (
            history(
                amount=D("152"),
                merchant_raw="SHOP&GO 123",
                merchant="Shop&Go",
                merchant_id="shop_go",
                occurred_at=at(date(2026, 6, 13), 10, 5),
            ),
        ),
    }
    return ctx(**(base | kw))
