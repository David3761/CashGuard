"""Write small placeholder data files into backend/data/ (B12, bomboe).

TEMPORARY: the real files come from danutu (E12: personas/<id>/profile.json, transactions.json),
David G. (D1: facts.json, rules.json; C1: merchants.json, products.json; D2: scenarios/).
They only need to keep the formats documented in app/db/seed.py. Deterministic output.

    uv run python scripts/placeholder_data.py
"""

import json
from datetime import date, timedelta
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
START = date(2026, 6, 15)


def write(path: str, content: object) -> None:
    target = DATA / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def at(day: date, hhmm: str) -> str:
    return f"{day.isoformat()}T{hhmm}:00+03:00"


MERCHANTS = [
    ("mega_image", "Mega Image", ["MEGA IMAGE"], "groceries", "5411", 85, False),
    ("shop_go", "Shop&Go", ["SHOP&GO", "SHOP & GO"], "groceries", "5411", 60, False),
    ("kaufland", "Kaufland", ["KAUFLAND"], "groceries", "5411", 250, True),
    ("profi", "Profi", ["PROFI"], "groceries", "5411", 45, False),
    ("carrefour", "Carrefour", ["CARREFOUR"], "groceries", "5411", 180, True),
    ("emag", "eMAG", ["PAYU*EMAG.RO", "EMAG"], "electronics", "5732", 400, True),
    ("altex", "Altex", ["ALTEX"], "electronics", "5732", 600, True),
    ("flanco", "Flanco", ["FLANCO"], "electronics", "5732", 500, True),
    ("glovo", "Glovo", ["GLOVO*ORDER", "GLOVO"], "food_delivery", "5814", 60, False),
    ("trattoria", "Trattoria Il Calcio", ["TRATTORIA IL CALCIO"], "restaurants", "5812", 90, False),
    ("wizz_air", "Wizz Air", ["WIZZ AIR", "WIZZAIR"], "travel", "4511", 450, False),
    ("dr_max", "Dr.Max", ["DR.MAX", "DR MAX"], "health_pharmacy", "5912", 70, False),
    ("spotify", "Spotify", ["SPOTIFY"], "subscriptions", "5815", 25, False),
    ("decathlon", "Decathlon", ["DECATHLON"], "sport", "5941", 150, True),
]

PRODUCTS = [
    {
        "id": "pusculita_flexibila",
        "name": "Pușculiță flexibilă",
        "kind": "flexible_pot",
        "rate": 0.035,
        "liquidity": "instant",
        "min_months": 0,
        "max_months": 12,
        "mock": True,
        "description": "Bani disponibili oricând; dobândă mică.",
    },
    {
        "id": "cont_economii",
        "name": "Cont de economii",
        "kind": "savings_account",
        "rate": 0.045,
        "liquidity": "notice",
        "min_months": 3,
        "max_months": 24,
        "mock": True,
        "description": "Retragere cu preaviz de câteva zile.",
    },
    {
        "id": "depozit_6_luni",
        "name": "Depozit 6 luni",
        "kind": "term_deposit",
        "rate": 0.055,
        "liquidity": "locked",
        "min_months": 6,
        "max_months": 6,
        "mock": True,
        "description": "Dobânda cea mai bună; banii stau blocați 6 luni.",
    },
]


def tx(day: date, hhmm: str, raw: str, amount: float, category: str, **kw: object) -> dict:
    return {
        "occurred_at": at(day, hhmm),
        "merchant_raw": raw,
        "amount": amount,
        "category": category,
        **kw,
    }


def matei_history() -> list[dict]:
    rows = [
        tx(
            date(2026, 6, 1),
            "09:00",
            "CHIRIE PROPRIETAR",
            2000,
            "housing_rent",
            purpose="essential_living",
        ),
        tx(date(2026, 6, 10), "08:00", "SALARIU ACME SRL", 7000, "income", direction="credit"),
    ]
    baskets = [82, 91, 79, 88, 85, 93, 77, 86, 84, 90, 81, 87]
    day, i = START - timedelta(days=21), 0
    while day < START:
        if day.weekday() < 4:  # Mon–Thu lunch at Mega near the office
            rows.append(
                tx(
                    day,
                    "12:40",
                    "MEGA IMAGE 0451 BUCURESTI",
                    baskets[i % 12],
                    "groceries",
                    purpose="essential_living",
                )
            )
            i += 1
        if day.weekday() in (1, 5):
            rows.append(
                tx(
                    day,
                    "20:30",
                    "GLOVO*ORDER 8812",
                    58 + i % 7,
                    "food_delivery",
                    purpose="unplanned_discretionary",
                )
            )
        day += timedelta(days=1)
    for friday, amount in ((date(2026, 6, 5), 95), (date(2026, 6, 12), 88)):
        rows.append(
            tx(
                friday,
                "13:10",
                "TRATTORIA IL CALCIO",
                amount,
                "restaurants",
                purpose="social_connection",
                annotation_source="answer",
                explanation="Prânz cu echipa",
            )
        )
    return sorted(rows, key=lambda r: r["occurred_at"])


PERSONAS = {
    "matei": {
        "profile": {
            "name": "Matei",
            "age": 26,
            "city": "București",
            "language": "ro",
            "tagline": "Junior developer, stă singur, strânge 10.000 lei",
            "household_scale": 1.0,
            "onboarded": True,
            "account": {"current_balance": 2850},
            "income_sources": [{"source": "Salariu", "amount": 7000, "day_of_month": 10}],
            "fixed_costs": [
                {"name": "Chirie", "amount": 2000, "day_of_month": 1},
                {"name": "Utilități", "amount": 350, "day_of_month": 15},
                {"name": "Telefon", "amount": 60, "day_of_month": 20},
                {"name": "Spotify", "amount": 25, "day_of_month": 5},
                {"name": "Sală", "amount": 180, "day_of_month": 3},
            ],
            "goal": {
                "amount": 10000,
                "deadline": "2026-12-31",
                "motivation": "Fond 10.000",
                "soft": True,
                "saved": 5200,
            },
            "last_week_probability": 0.72,
        },
        "facts": [
            {
                "type": "occupation",
                "value": {"title": "junior developer", "work_mode": "hybrid"},
                "text": "Sunt junior developer, la birou marți–joi",
            },
            {
                "type": "housing",
                "value": {"kind": "rent", "lives_alone": True},
                "text": "Stau singur",
            },
            {
                "type": "priority",
                "value": {
                    "category": "entertainment",
                    "label": "concerte",
                    "priority": "protected",
                },
                "text": "Concertele nu le tai",
            },
            {
                "type": "priority",
                "value": {"category": "food_delivery", "priority": "reduce"},
                "text": "Aș vrea să comand mai rar",
            },
        ],
        "rules": [
            {
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
        ],
        "transactions": matei_history(),
    },
    "andrei": {
        "profile": {
            "name": "Andrei",
            "age": 31,
            "city": "București",
            "language": "ro",
            "tagline": "Analist sportiv, lucrează de acasă",
            "household_scale": 1.5,
            "onboarded": True,
            "account": {"current_balance": 6400},
            "income_sources": [{"source": "Salariu", "amount": 9000, "day_of_month": 5}],
            "fixed_costs": [{"name": "Chirie", "amount": 2600, "day_of_month": 1}],
            "goal": {
                "amount": 15000,
                "deadline": "2027-03-31",
                "motivation": "Avans apartament",
                "soft": True,
                "saved": 6100,
            },
        },
        "facts": [
            {
                "type": "occupation",
                "value": {"title": "analist sportiv", "work_mode": "remote"},
                "text": "Sunt analist sportiv, lucrez de acasă",
                "signatures": [
                    {
                        "effect": "explains",
                        "category": "electronics",
                        "merchant_hints": ["eMAG", "Altex", "Flanco"],
                        "item_keywords": ["televizor", "TV", "monitor", "soundbar"],
                        "amount_min": 1500,
                        "amount_max": 9000,
                        "replacement_cycle_days": 900,
                        "purpose": "work_tool",
                        "strength": 0.9,
                    },
                    {
                        "effect": "explains",
                        "category": "subscriptions",
                        "merchant_hints": ["Digi Sport", "Prima Sport", "DAZN", "Voyo"],
                        "purpose": "work_tool",
                        "strength": 0.9,
                    },
                ],
            },
            {
                "type": "household_member",
                "value": {"role": "adult", "relation": "partener"},
                "text": "Stau cu partenera mea",
            },
        ],
        "transactions": [
            tx(date(2026, 6, 5), "08:00", "SALARIU MEDIA SRL", 9000, "income", direction="credit"),
            tx(
                date(2026, 6, 13),
                "18:20",
                "MEGA IMAGE 0112 BUCURESTI",
                118,
                "groceries",
                purpose="household_care",
            ),
        ],
    },
    "bianca": {
        "profile": {
            "name": "Bianca",
            "age": 22,
            "city": "Iași",
            "language": "ro",
            "tagline": "Studentă și barista part-time",
            "household_scale": 1.0,
            "onboarded": True,
            "account": {"current_balance": 740},
            "income_sources": [{"source": "Barista", "amount": 2800, "day_of_month": 15}],
            "fixed_costs": [{"name": "Chirie (partea mea)", "amount": 700, "day_of_month": 1}],
            "goal": {
                "amount": 3000,
                "deadline": "2026-08-31",
                "motivation": "Vara la mare",
                "soft": False,
                "saved": 900,
            },
        },
        "facts": [
            {"type": "occupation", "value": {"title": "studentă"}, "text": "Sunt studentă"},
            {
                "type": "employment",
                "value": {"job": "barista", "part_time": True},
                "text": "Lucrez part-time ca barista",
            },
            {
                "type": "income_pattern",
                "value": {"irregular": True, "tips": True},
                "text": "Câștig din bacșiș, variază",
            },
        ],
        "transactions": [
            tx(
                date(2026, 6, 14),
                "17:45",
                "PROFI 112 IASI",
                38,
                "groceries",
                purpose="essential_living",
            )
        ],
    },
    "ioana": {
        "profile": {
            "name": "Ioana",
            "age": 38,
            "city": "Cluj-Napoca",
            "language": "ro",
            "tagline": "Contabilă, familie de 4",
            "household_scale": 2.1,
            "onboarded": True,
            "account": {"current_balance": 9800},
            "income_sources": [{"source": "Venit gospodărie", "amount": 15500, "day_of_month": 10}],
            "fixed_costs": [{"name": "Rată credit", "amount": 3200, "day_of_month": 15}],
            "goal": {
                "amount": 12000,
                "deadline": "2026-12-31",
                "motivation": "Fond de urgență",
                "soft": True,
                "saved": 4300,
            },
        },
        "facts": [
            {"type": "occupation", "value": {"title": "contabilă"}, "text": "Sunt contabilă"},
            {
                "type": "household_member",
                "value": {"role": "adult", "relation": "partener"},
                "text": "Suntem 4 acasă",
            },
            {
                "type": "household_member",
                "value": {"role": "child", "age": 7},
                "text": "Fiica, 7 ani",
            },
            {
                "type": "household_member",
                "value": {"role": "child", "age": 11},
                "text": "Fiul, 11 ani",
            },
        ],
        "transactions": [
            tx(
                date(2026, 6, 13),
                "10:05",
                "SHOP&GO 123",
                152,
                "groceries",
                purpose="household_care",
            )
        ],
    },
    "alex": {
        "profile": {
            "name": "Alex",
            "age": 24,
            "city": "București",
            "language": "ro",
            "tagline": "Cont nou: onboarding live",
            "household_scale": 1.0,
            "onboarded": False,
            "account": {"current_balance": 1200},
        },
        "facts": [],
        "transactions": [],
    },
}

SCENARIOS = {
    "matei_mega_500": (
        "matei",
        "MEGA IMAGE 0451 BUCURESTI",
        "5411",
        500,
        "groceries",
        "13:05",
        None,
    ),
    "matei_shopgo_350": ("matei", "SHOP&GO 123 BUCURESTI", "5411", 350, "groceries", "18:30", None),
    "andrei_tv": (
        "andrei",
        "PAYU*EMAG.RO",
        "5732",
        4500,
        "electronics",
        "11:20",
        [{"name": 'Televizor 65"', "qty": 1, "amount": 4500}],
    ),
    "bianca_tv": (
        "bianca",
        "PAYU*EMAG.RO",
        "5732",
        4500,
        "electronics",
        "11:20",
        [{"name": 'Televizor 65"', "qty": 1, "amount": 4500}],
    ),
    "bianca_tv_noitems": ("bianca", "PAYU*EMAG.RO", "5732", 4500, "electronics", "11:20", None),
    "matei_flight": ("matei", "WIZZ AIR WIZZAIR.COM", "4511", 900, "travel", "21:15", None),
    "matei_friday_lunch": (
        "matei",
        "TRATTORIA IL CALCIO",
        "5812",
        95,
        "restaurants",
        "13:10",
        None,
    ),
    "ioana_shopgo_350": ("ioana", "SHOP&GO 77 CLUJ", "5411", 350, "groceries", "10:30", None),
}


def main() -> None:
    write(
        "merchants.json",
        [
            {
                "id": i,
                "canonical_name": n,
                "aliases": a,
                "category": c,
                "mcc": mcc,
                "typical_basket": basket,
                "multi_category": multi,
            }
            for i, n, a, c, mcc, basket, multi in MERCHANTS
        ],
    )
    write("products.json", PRODUCTS)
    for pid, data in PERSONAS.items():
        write(f"personas/{pid}/profile.json", data["profile"])
        write(f"personas/{pid}/facts.json", data["facts"])
        write(f"personas/{pid}/transactions.json", data["transactions"])
        if "rules" in data:
            write(f"personas/{pid}/rules.json", data["rules"])
    for sid, (persona, raw, mcc, amount, category, time, items) in SCENARIOS.items():
        write(
            f"scenarios/{sid}.json",
            {
                "id": sid,
                "persona": persona,
                "merchant_raw": raw,
                "mcc": mcc,
                "amount": amount,
                "category": category,
                "day_offset": 0,
                "time": time,
                "items": items,
            },
        )


if __name__ == "__main__":
    main()
