"""Elena, the heavy persona: four years of history and data in every table the app reads.

Writes `data/personas/elena/{config,facts,rules,extras}.json`, then runs the E12 generator
(`scripts/generate_personas.py`) for `profile.json` + `transactions.json`. Deterministic: one
seeded `random.Random`, sorted JSON, so two runs give identical bytes. The chat history quotes
real totals from the generated transactions, so it agrees with what the tools return.

    uv run python scripts/build_elena.py

Elena (34, Cluj-Napoca): product manager plus freelance design, married to Radu, two children
(Ana 7, Luca 3), a dog, a mortgage and a car loan. Goal: a new kitchen (30 000 lei, June 2027).
"""

import importlib.util
import json
import random
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any
from zoneinfo import ZoneInfo

BACKEND = Path(__file__).resolve().parents[1]
FOLDER = BACKEND / "data" / "personas" / "elena"
BUCHAREST = ZoneInfo("Europe/Bucharest")
HISTORY_FROM = date(2022, 6, 15)
LAST_DAY = date(2026, 6, 14)  # the day before the demo date (SIM_START_DATE)
SEED = 606


def load_generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "generate_personas", BACKEND / "scripts" / "generate_personas.py"
    )
    if spec is None or spec.loader is None:
        raise ImportError("scripts/generate_personas.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def lei(x: Decimal | float | str) -> str:
    """1234.5 → "1.234,50" (how the coach writes amounts in Romanian)."""
    whole, cents = f"{Decimal(str(x)):.2f}".split(".")
    return f"{int(whole):,}".replace(",", ".") + "," + cents


def at(d: date, hour: int, minute: int = 0) -> str:
    return datetime.combine(d, time(hour, minute), tzinfo=BUCHAREST).isoformat()


# ── config.json (the generator's input) ─────────────────────────────────────


def stream(name: str, kind: str, merchants: list[str] | str, category: str, **kw: Any) -> dict:
    return {"name": name, "kind": kind, "merchant_raw": merchants, "category": category, **kw}


STREAMS = [
    stream(
        "kaufland_weekly",
        "weekly",
        ["KAUFLAND 1203 CLUJ", "KAUFLAND MARASTI CLUJ"],
        "groceries",
        per_week=[1, 2],
        weekdays=[5, 6],
        hours=[10, 13],
        median=330,
        sigma=0.3,
        min=120,
        max=1100,
        mcc=5411,
    ),
    stream(
        "lidl_midweek",
        "weekly",
        ["LIDL 0213 CLUJ-NAPOCA", "LIDL GHEORGHENI CLUJ"],
        "groceries",
        per_week=[1, 2],
        weekdays=[1, 2, 3, 4],
        hours=[17, 20],
        median=120,
        sigma=0.35,
        min=30,
        max=480,
        mcc=5411,
    ),
    stream(
        "bakery",
        "every",
        ["PANEMAR 014 CLUJ", "LA BONTON PATISERIE"],
        "groceries",
        weekdays=[1, 2, 3, 4, 5, 6],
        probability=0.55,
        hours=[7, 9],
        median=22,
        sigma=0.3,
        min=6,
        max=70,
        mcc=5462,
    ),
    stream(
        "coffee",
        "every",
        ["MAKERS SPECIALTY COFFEE", "OUTPOST COFFEE CLUJ", "STARBUCKS IULIUS MALL"],
        "restaurants",
        weekdays=[1, 2, 3, 4, 5],
        probability=0.5,
        hours=[9, 11],
        range=[12, 26],
        mcc=5814,
    ),
    stream(
        "office_lunch",
        "every",
        ["BISTRO NORDIC CAFETERIA", "SALAD BOX CLUJ", "SUBWAY CLUJ"],
        "restaurants",
        weekdays=[2, 3, 4],
        probability=0.6,
        hours=[12, 14],
        median=45,
        sigma=0.25,
        min=18,
        max=95,
        mcc=5812,
    ),
    stream(
        "fuel",
        "weekly",
        ["OMV 2201 CLUJ", "PETROM FLORESTI", "MOL CALEA TURZII"],
        "fuel",
        per_week=[1, 1],
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        hours=[7, 20],
        median=260,
        sigma=0.2,
        min=120,
        max=520,
        mcc=5541,
    ),
    stream(
        "pharmacy",
        "weekly",
        ["CATENA FARMACIA 112", "DONA FARMACIA 51", "HELP NET FARMACIE"],
        "health_pharmacy",
        per_week=[0, 1],
        weekdays=[1, 2, 3, 4, 5, 6],
        hours=[9, 20],
        median=95,
        sigma=0.5,
        min=15,
        max=450,
        mcc=5912,
    ),
    stream(
        "kids_shop",
        "weekly",
        ["SMYK CLUJ IULIUS", "NORIEL VIVO CLUJ", "DECATHLON CLUJ", "KINDERLAND CLUJ"],
        "kids",
        per_week=[0, 2],
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        hours=[10, 20],
        median=110,
        sigma=0.55,
        min=20,
        max=700,
        mcc=5641,
    ),
    stream(
        "kids_weekend",
        "weekly",
        ["LOCUL DE JOACA KIDDO", "GRADINA ZOOLOGICA CLUJ", "AQUAPARK ARENA CLUJ"],
        "kids",
        per_week=[0, 1],
        weekdays=[6, 7],
        hours=[10, 18],
        median=90,
        sigma=0.35,
        min=25,
        max=260,
        mcc=7996,
    ),
    stream(
        "pets",
        "weekly",
        ["ANIMAX CLUJ", "PET MART VIVO", "CABINET VETERINAR VETMED"],
        "pets",
        per_week=[0, 1],
        weekdays=[1, 2, 3, 4, 5, 6],
        hours=[10, 19],
        median=160,
        sigma=0.4,
        min=30,
        max=650,
        mcc=5995,
    ),
    stream(
        "weekend_restaurant",
        "weekly",
        ["RESTAURANT ROATA CLUJ", "SAMSARA FOODHOUSE", "LOCUL DIN CENTRU", "MARTY CAFE CLUJ"],
        "restaurants",
        per_week=[0, 1],
        weekdays=[5, 6, 7],
        hours=[13, 22],
        median=240,
        sigma=0.35,
        min=80,
        max=750,
        mcc=5812,
    ),
    stream(
        "delivery",
        "weekly",
        ["GLOVO*ORDER 7731", "TAZZ BY EMAG", "WOLT CLUJ"],
        "food_delivery",
        per_week=[0, 2],
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        hours=[18, 22],
        median=110,
        sigma=0.3,
        min=35,
        max=320,
        mcc=5814,
    ),
    stream(
        "clothes",
        "weekly",
        ["H&M IULIUS MALL", "ZARA VIVO CLUJ", "ANSWEAR.RO", "FASHIONDAYS.RO", "PEPCO CLUJ"],
        "clothing",
        per_week=[0, 1],
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        hours=[11, 21],
        median=200,
        sigma=0.6,
        min=40,
        max=1500,
        mcc=5651,
    ),
    stream(
        "household",
        "weekly",
        ["IKEA CLUJ", "DEDEMAN CLUJ", "JYSK CLUJ", "LEROY MERLIN CLUJ"],
        "household_goods",
        per_week=[0, 1],
        weekdays=[5, 6, 7],
        hours=[10, 19],
        median=190,
        sigma=0.6,
        min=20,
        max=2000,
        mcc=5200,
    ),
    stream(
        "personal_care",
        "weekly",
        ["DM DROGERIE MARKT", "SEPHORA IULIUS", "SALON BEAUTY ROOM CLUJ"],
        "personal_care",
        per_week=[0, 1],
        weekdays=[1, 2, 3, 4, 5, 6],
        hours=[10, 20],
        median=85,
        sigma=0.45,
        min=15,
        max=420,
        mcc=5977,
    ),
    stream(
        "rides",
        "weekly",
        ["BOLT.EU/O/2304", "UBER *TRIP", "CTP CLUJ BILET", "PARCARE CLUJ SMS"],
        "transport",
        per_week=[0, 3],
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        hours=[8, 23],
        median=24,
        sigma=0.4,
        min=5,
        max=90,
        mcc=4121,
    ),
    stream(
        "going_out",
        "weekly",
        ["CINEMA CITY IULIUS", "IABILET.RO", "ENTERTIX.RO", "TEATRUL NATIONAL CLUJ"],
        "entertainment",
        per_week=[0, 1],
        weekdays=[5, 6, 7],
        hours=[16, 21],
        median=120,
        sigma=0.4,
        min=30,
        max=400,
        mcc=7832,
    ),
    stream(
        "books",
        "weekly",
        ["CARTURESTI CLUJ", "LIBRARIA ESTE", "ELEFANT.RO"],
        "books",
        per_week=[0, 1],
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        hours=[12, 21],
        median=75,
        sigma=0.4,
        min=20,
        max=260,
        mcc=5942,
    ),
    stream(
        "gadgets",
        "every",
        ["EMAG.RO", "ALTEX CLUJ", "FLANCO VIVO CLUJ"],
        "electronics",
        weekdays=[1, 2, 3, 4, 5, 6, 7],
        probability=0.02,
        hours=[12, 22],
        median=420,
        sigma=0.8,
        min=40,
        max=4500,
        mcc=5732,
    ),
    stream(
        "gifts",
        "weekly",
        ["FLORARIA ANTHURIUM CLUJ", "CADOURI.RO", "BOOKZONE CADOURI"],
        "gifts",
        per_week=[0, 1],
        weekdays=[1, 2, 3, 4, 5, 6],
        hours=[11, 19],
        median=120,
        sigma=0.5,
        min=30,
        max=480,
        mcc=5992,
    ),
    stream(
        "parents_groceries",
        "every",
        "PROFI 1450 FLORESTI",
        "groceries",
        weekdays=[7],
        probability=0.35,
        hours=[10, 12],
        median=180,
        sigma=0.3,
        min=60,
        max=420,
        mcc=5411,
    ),
    stream(
        "donation",
        "monthly",
        "SALVATI COPIII ROMANIA",
        "other",
        day_of_month=28,
        amount=50,
        hours=[9, 10],
    ),
    stream(
        "google_one",
        "monthly",
        "GOOGLE *GOOGLE ONE",
        "subscriptions",
        day_of_month=15,
        amount=15,
        mcc=5815,
        hours=[3, 4],
    ),
    stream(
        "icloud",
        "monthly",
        "APPLE.COM/BILL ICLOUD",
        "subscriptions",
        day_of_month=19,
        amount=15,
        mcc=5815,
        hours=[3, 4],
    ),
]

FIXED_COSTS = [
    ("Rată ipotecă", "3150", 5, "RATA CREDIT IPOTECAR BT 77120", "housing_rent", None, 0),
    ("Întreținere bloc", "430", 18, "ASOCIATIA PROPRIETARI GHEORGHENI", "utilities", None, 20),
    ("Curent", "260", 14, "ELECTRICA FURNIZARE SA", "utilities", 4900, 15),
    ("Gaz", "190", 16, "ENGIE ROMANIA SA", "utilities", 4900, 35),
    ("Internet + TV", "95", 21, "DIGI ROMANIA SA", "telecom", 4899, 0),
    ("Telefoane", "145", 20, "ORANGE ROMANIA SA", "telecom", 4814, 0),
    ("Rată mașină", "980", 12, "RATA LEASING AUTO UNICREDIT", "transport", None, 0),
    ("Grădiniță Luca", "1250", 2, "GRADINITA RAZA DE SOARE SRL", "kids", 8211, 0),
    ("After-school Ana", "950", 2, "AFTER SCHOOL CLEVER KIDS", "kids", 8299, 0),
    ("Netflix", "62", 7, "NETFLIX.COM", "subscriptions", 4899, 0),
    ("Spotify Family", "42", 9, "SPOTIFY P3B71D2", "subscriptions", 5815, 0),
    ("Sală", "230", 4, "STAY FIT GYM CLUJ", "sport", 7997, 0),
    ("Asigurare locuință", "75", 22, "GROUPAMA ASIGURARI LOCUINTA", "other", 6300, 0),
    ("Înot Ana", "320", 6, "CLUB SPORTIV POLI CLUJ INOT", "sport", 7997, 0),
    ("Engleză Ana", "380", 6, "ENGLISH TIME CLUJ", "education", 8299, 0),
]

VACATIONS = [  # (first day, last day, place, booking, booked on, local merchants)
    (
        date(2022, 8, 6),
        date(2022, 8, 14),
        "Mamaia",
        "1900",
        date(2022, 6, 20),
        ["PENSIUNEA MAMAIA NORD", "CARREFOUR MAMAIA", "RESTAURANT ZANZIBAR MAMAIA"],
    ),
    (
        date(2023, 8, 12),
        date(2023, 8, 22),
        "Thassos",
        "4200",
        date(2023, 6, 10),
        ["AEGEAN FERRIES KERAMOTI", "MASOUTIS THASSOS", "TAVERNA KYMA THASSOS"],
    ),
    (
        date(2024, 7, 20),
        date(2024, 7, 31),
        "Split",
        "5200",
        date(2024, 6, 10),
        ["KONZUM SPLIT", "RESTORAN DALMACIJA SPLIT", "JADROLINIJA FERRY"],
    ),
    (
        date(2025, 8, 2),
        date(2025, 8, 13),
        "Halkidiki",
        "6100",
        date(2025, 6, 10),
        ["MY MARKET HALKIDIKI", "TAVERNA THALASSA", "BOAT TRIP KASSANDRA"],
    ),
]
SKI = (date(2025, 2, 15), date(2025, 2, 20))
EASTER = {
    2023: date(2023, 4, 16),
    2024: date(2024, 5, 5),
    2025: date(2025, 4, 20),
    2026: date(2026, 4, 12),
}
BLACK_FRIDAY = {
    2022: ("EMAG.RO BLACK FRIDAY LAPTOP", "3400", "electronics"),
    2023: ("ALTEX TV BLACK FRIDAY", "2600", "electronics"),
    2024: ("FLANCO FRIGIDER BLACK FRIDAY", "3200", "household_goods"),
    2025: ("EMAG.RO BLACK FRIDAY TELEFON", "2900", "electronics"),
}
LOCAL = [
    "kaufland_weekly",
    "lidl_midweek",
    "bakery",
    "coffee",
    "office_lunch",
    "delivery",
    "rides",
    "parents_groceries",
    "weekend_restaurant",
    "kids_weekend",
    "going_out",
    "personal_care",
]


def last_friday_of_november(year: int) -> date:
    d = date(year, 11, 30)
    return d - timedelta(days=(d.weekday() - 4) % 7)


def calendar(rng: random.Random) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    def ev(d: date, amount: float | str, merchant: str, category: str, **kw: Any) -> None:
        if HISTORY_FROM <= d <= LAST_DAY:
            events.append(
                {
                    "date": d.isoformat(),
                    "amount": str(Decimal(str(amount)).quantize(Decimal("1"))),
                    "merchant_raw": merchant,
                    "category": category,
                    **kw,
                }
            )

    for year in range(2022, 2027):
        up = 1 + 0.06 * (year - 2022)  # four years of prices going up
        ev(date(year, 1, 14), 1350 * up, "GROUPAMA ASIGURARI RCA", "transport", mcc=6300)
        ev(date(year, 2, 14), 170 * up, "FLORARIA ANTHURIUM CLUJ", "gifts", mcc=5992)
        ev(date(year, 3, 1), 1300 * up, "KIDDO PARTY ZI DE NASTERE", "kids", mcc=7996)
        ev(date(year, 3, 7), 150 * up, "FLORARIA MARTISOR CLUJ", "gifts", mcc=5992)
        if year in EASTER:
            ev(EASTER[year] - timedelta(days=2), 360 * up, "PIATA MARASTI PASTE", "groceries")
            ev(EASTER[year] - timedelta(days=3), 240 * up, "SMYK CADOURI PASTE", "gifts", mcc=5641)
        if year >= 2023:
            ev(date(year, 5, 10), 1500 * up, "ELECTRIC CASTLE BILETE", "entertainment", mcc=7922)
        ev(date(year, 7, 19), 600 * up, "SAMSARA FOODHOUSE ZI NASTERE", "restaurants", mcc=5812)
        ev(date(year, 8, 27), 650 * up, "CARREFOUR RECHIZITE SCOALA", "education", mcc=5943)
        ev(date(year, 9, 14), 900 * up, "LOCUL DE JOACA KIDDO PARTY", "kids", mcc=7996)
        ev(date(year, 10, 5), 1300 * up, "SERVICE AUTO DACIA PLUS CLUJ", "transport", mcc=7538)
        if year % 2 == 0:
            ev(date(year, 10, 20), 170 * up, "ITP AUTO TEST CLUJ", "transport", mcc=7549)
        ev(date(year, 10, 28), 450 * up, "DECATHLON CADOU RADU", "gifts", mcc=5941)
        ev(
            date(year, 11, 5),
            1900 if year == 2023 else 220 * up,
            "VULCANIZARE ANVELOPE CLUJ",
            "transport",
            mcc=7538,
        )
        if year in BLACK_FRIDAY:
            merchant, amount, category = BLACK_FRIDAY[year]
            ev(last_friday_of_november(year), amount, merchant, category, mcc=5732)
        ev(date(year, 12, 8), 220 * up, "TARGUL DE CRACIUN CLUJ", "entertainment")
        ev(date(year, 12, 15), 850 * up, "SMYK CADOURI CRACIUN", "gifts", mcc=5641)
        ev(date(year, 12, 18), 560 * up, "ALLEGRO.RO CADOURI", "gifts")
        ev(date(year, 12, 20), 280 * up, "CARTURESTI CADOURI", "books", mcc=5942)
        ev(date(year, 12, 31), 900 * up, "RESTAURANT REVELION CLUJ", "restaurants", mcc=5812)
        for _ in range(2):  # the dentist, twice a year
            d = date(year, 1, 1) + timedelta(days=rng.randrange(365))
            ev(d, rng.randrange(400, 1800, 10), "DENTAL ART CLUJ", "health_pharmacy", mcc=8021)
    for first, last, place, booking, booked, local in VACATIONS:
        ev(booked, booking, f"BOOKING.COM HOTEL {place.upper()}", "travel", mcc=4722)
        for i in range((last - first).days + 1):
            d = first + timedelta(days=i)
            ev(
                d,
                rng.randrange(120, 420, 5),
                local[i % 3],
                "groceries" if i % 3 == 1 else "travel" if i % 3 == 0 else "restaurants",
            )
    ev(date(2025, 1, 20), 2600, "BOOKING.COM POIANA BRASOV", "travel", mcc=4722)
    ev(date(2025, 2, 16), 880, "SKIPASS POIANA BRASOV", "sport", mcc=7997)
    ev(date(2025, 2, 17), 600, "SCOALA SCHI POIANA BRASOV", "sport", mcc=7997)
    ev(date(2024, 4, 20), 560, "DEDEMAN CLUJ GRADINA", "household_goods", mcc=5200)
    ev(date(2026, 5, 22), 1500, "BOOKING.COM AVANS CORFU", "travel", mcc=4722)
    ev(date(2026, 6, 6), 340, "DEDEMAN MOSTRE GRESIE", "household_goods", mcc=5200)
    return sorted(events, key=lambda e: (e["date"], e["merchant_raw"]))


def spikes() -> list[dict[str, Any]]:
    out = []
    for year in range(2022, 2027):
        out += [
            {
                "stream": "kaufland_weekly",
                "from": f"{year}-12-14",
                "to": f"{year}-12-23",
                "multiplier": 1.8,
            },
            {
                "stream": "kids_shop",
                "from": f"{year}-08-20",
                "to": f"{year}-09-12",
                "multiplier": 2.3,
            },
            {
                "stream": "clothes",
                "from": f"{year}-11-20",
                "to": f"{year}-11-30",
                "multiplier": 1.7,
            },
            {
                "stream": "pharmacy",
                "from": f"{year}-01-10",
                "to": f"{year}-02-20",
                "multiplier": 1.6,
            },
        ]
    return out


def quiet() -> list[dict[str, Any]]:
    out = [{"from": a.isoformat(), "to": b.isoformat(), "streams": LOCAL} for a, b, *_ in VACATIONS]
    out.append({"from": SKI[0].isoformat(), "to": SKI[1].isoformat(), "streams": LOCAL})
    out += [
        {
            "from": f"{y}-12-24",
            "to": f"{y}-12-28",
            "streams": ["coffee", "office_lunch", "lidl_midweek"],
        }
        for y in range(2022, 2026)
    ]
    # January 2026: a month without delivery (her own resolution, see the `reduce` fact)
    out.append({"from": "2026-01-05", "to": "2026-01-31", "streams": ["delivery"]})
    return out


GOAL_SAVED = "17400"
POTS = [  # name, kind, target, saved, deadline, first month of the saving
    ("Fond de urgență", "emergency", "25000", "21000", None, date(2022, 7, 1)),
    ("Vacanță Corfu 2026", "event", "8000", "5600", "2026-08-01", date(2025, 9, 1)),
    ("Service & RCA mașină", "custom", "4000", "2300", "2026-10-01", date(2025, 10, 1)),
    ("Tabără Ana", "event", "1800", "1200", "2026-07-10", date(2026, 1, 1)),
    ("Crăciun 2026", "event", "3000", "900", "2026-12-15", date(2026, 4, 1)),
]
GOAL_POT = ("Bucătărie nouă", date(2025, 1, 1))


def config(rng: random.Random) -> dict[str, Any]:
    return {
        "id": "elena",
        "seed": SEED,
        "history_from": HISTORY_FROM.isoformat(),
        "user": {
            "name": "Elena",
            "age": 34,
            "city": "Cluj-Napoca",
            "language": "ro",
            "coach_style": "warm",
        },
        "current_balance": "9340.55",
        "income_sources": [
            {
                "source": "Salariu",
                "amount": "11500",
                "day_of_month": 10,
                "merchant_raw": "SALARIU NORDIC SOFT SRL",
            },
            {
                "source": "Salariu Radu",
                "amount": "7050",
                "day_of_month": 15,
                "merchant_raw": "SALARIU CLUJ MEDICAL SRL",
            },
            {
                "source": "Proiecte freelance",
                "amount": "2200",
                "day_of_month": 25,
                "merchant_raw": "TRANSFER PIXEL DESIGN STUDIO",
            },
            {
                "source": "Alocații copii",
                "amount": "680",
                "day_of_month": 8,
                "merchant_raw": "ALOCATIE STAT AJPIS CLUJ",
            },
        ],
        "fixed_costs": [
            {
                "name": n,
                "amount": a,
                "day_of_month": d,
                "merchant_raw": mr,
                "category": c,
                **({"mcc": mcc} if mcc else {}),
                **({"jitter_pct": j} if j else {}),
            }
            for n, a, d, mr, c, mcc, j in FIXED_COSTS
        ],
        "goal": {
            "amount": "30000",
            "deadline": "2027-06-30",
            "motivation": "Bucătărie nouă",
            "hard_deadline": False,
        },
        "goal_pot": {"name": GOAL_POT[0], "saved": GOAL_SAVED},
        "pots": [
            {"name": n, "kind": k, "target": t, "saved": s, "deadline": dl}
            for n, k, t, s, dl, _ in POTS
        ],
        "plan_preferences": {"buffer_pct": "0.12"},
        "streams": STREAMS,
        "spikes": spikes(),
        "quiet": quiet(),
        "calendar": calendar(rng),
        "answered": [
            {
                "stream": "parents_groceries",
                "last": 12,
                "purpose": "household_care",
                "label": "Cumpărături pentru părinți",
            },
            {
                "stream": "weekend_restaurant",
                "last": 4,
                "purpose": "social_connection",
                "label": "Ieșit cu prietenii",
            },
            {
                "stream": "kids_weekend",
                "last": 5,
                "purpose": "household_care",
                "label": "Weekend cu copiii",
            },
        ],
        "receipt_share": 0.25,
        "receipt_items": {
            "kaufland_weekly": [
                "Lapte",
                "Ouă",
                "Pâine",
                "Piept de pui",
                "Mere",
                "Iaurt copii",
                "Detergent",
                "Scutece",
                "Cafea",
                "Brânză",
                "Roșii",
                "Paste",
            ],
            "lidl_midweek": [
                "Banane",
                "Iaurt",
                "Pâine integrală",
                "Castraveți",
                "Șuncă",
                "Apă plată",
                "Biscuiți copii",
                "Unt",
            ],
            "kids_shop": [
                "Tricou",
                "Pantaloni",
                "Puzzle",
                "Lego",
                "Carte de colorat",
                "Șosete",
                "Încălțăminte sport",
            ],
            "pharmacy": [
                "Nurofen copii",
                "Vitamina D",
                "Ser fiziologic",
                "Plasturi",
                "Paracetamol",
            ],
            "household": ["Raft", "Cutii depozitare", "Lampă", "Prosoape", "Vopsea", "Becuri"],
        },
    }


# ── facts.json and rules.json ───────────────────────────────────────────────


def fact(type_: str, value: dict[str, Any], text: str, **kw: Any) -> dict[str, Any]:
    return {
        "type": type_,
        "value": value,
        "text": text,
        "source": "seed",
        "status": "confirmed",
        "confidence": 0.95,
        "persistence": "permanent",
        "valid_from": "2022-06-01",
        **kw,
    }


FACTS = [
    fact(
        "occupation",
        {"title": "product manager", "work_mode": "birou marți-joi", "employer": "Nordic Soft"},
        "Sunt product manager la Nordic Soft, merg la birou marți, miercuri și joi",
    ),
    fact("employment", {"kind": "employee"}, "Sunt angajată"),
    fact(
        "income_pattern",
        {"irregular": False, "note": "freelance design, ~2.200 lei pe 25"},
        "Mai fac proiecte de design freelance, cam 2.200 de lei pe lună",
    ),
    fact("household_member", {"role": "adult", "relation": "partner"}, "Stau cu soțul meu, Radu"),
    fact(
        "household_member",
        {"role": "child", "age": 7, "relation": "daughter"},
        "Fiica mea, Ana, are 7 ani",
    ),
    fact(
        "household_member",
        {"role": "child", "age": 3, "relation": "son"},
        "Fiul meu, Luca, are 3 ani",
        valid_from="2022-09-14",
    ),
    fact("pet", {"species": "câine"}, "Avem un câine, Bruno"),
    fact("housing", {"kind": "own", "note": "mortgage"}, "Avem apartamentul nostru, plătim rata"),
    fact("city", {"name": "Cluj-Napoca"}, "Stăm în Cluj"),
    fact("vehicle", {"kind": "car", "fuel": "benzină"}, "Avem o mașină pe benzină, în leasing"),
    fact("commute", {"mode": "car"}, "Merg la birou cu mașina"),
    fact("activity", {"name": "sală", "per_week": 3}, "Merg la sală de trei ori pe săptămână"),
    fact("activity", {"name": "înot Ana", "per_week": 2}, "Ana face înot de două ori pe săptămână"),
    fact("activity", {"name": "engleză Ana", "per_week": 2}, "Ana face engleză după școală"),
    fact(
        "social_pattern",
        {"name": "prânz cu colegii", "weekdays": [2, 3, 4]},
        "Mănânc cu colegii în zilele de birou",
    ),
    fact(
        "social_pattern",
        {"name": "ieșit cu prietenii", "weekdays": [5, 6]},
        "Vinerea sau sâmbăta ieșim cu prietenii",
    ),
    fact(
        "rhythm",
        {"name": "zile la birou", "weekdays": [2, 3, 4]},
        "Sunt la birou marți, miercuri și joi",
    ),
    fact(
        "rhythm",
        {"name": "cumpărături mari", "weekdays": [5, 6]},
        "Facem cumpărăturile mari vineri sau sâmbătă",
    ),
    fact(
        "rhythm",
        {"name": "la părinți", "weekdays": [7]},
        "Duminica mergem la părinții mei și le duc cumpărături",
    ),
    fact(
        "priority",
        {"category": "kids", "priority": "protected", "label": "copiii"},
        "La copii nu tai nimic",
    ),
    fact(
        "priority",
        {"category": "travel", "priority": "protected", "label": "vacanța de vară"},
        "Vacanța de vară e sfântă",
    ),
    fact(
        "priority",
        {"category": "concerts", "priority": "protected", "label": "Electric Castle"},
        "Electric Castle e tradiția noastră",
    ),
    fact(
        "priority",
        {"category": "food_delivery", "priority": "reduce"},
        "Vreau să comand mai rar mâncare",
    ),
    fact(
        "priority",
        {"category": "clothing", "priority": "reduce"},
        "Vreau să cumpăr mai puține haine",
    ),
    fact(
        "life_event",
        {"name": "Electric Castle", "months": [7]},
        "În iulie mergem la Electric Castle",
        persistence="recurring",
    ),
    fact(
        "life_event",
        {"name": "vacanța de vară", "months": [8]},
        "În august plecăm în vacanță",
        persistence="recurring",
    ),
    fact(
        "life_event",
        {"name": "Crăciun", "months": [12]},
        "Decembrie e scump, cu cadourile",
        persistence="recurring",
    ),
    fact(
        "life_event",
        {"name": "ziua Anei", "months": [3]},
        "Ana își serbează ziua în martie",
        persistence="recurring",
    ),
    fact(
        "life_event",
        {"name": "începutul școlii", "months": [9]},
        "În septembrie începe școala",
        persistence="recurring",
    ),
    fact(
        "custom",
        {"description": "Renovăm bucătăria în 2027"},
        "Strângem pentru bucătărie, vrem s-o refacem în 2027",
        valid_from="2025-01-01",
    ),
]


def rule(
    match: dict[str, Any], purpose: str, label: str, hits: int, last_hit: str, share: float = 1.0
) -> dict[str, Any]:
    return {
        "kind": "classify",
        "match": {"merchant_id": None, **match},
        "outcome": {"purpose": purpose, "label": label, "own_share_ratio": share},
        "confidence": round(min(0.95, 0.55 + 0.05 * hits), 2),
        "hits": hits,
        "misses": 0,
        "source": "learned",
        "active": True,
        "created_at": "2025-11-04T13:10:00+02:00",
        "last_hit_at": last_hit,
    }


RULES = [
    rule(
        {
            "category": "restaurants",
            "weekdays": [2, 3, 4],
            "from": "12:00",
            "to": "14:30",
            "amount_min": 20,
            "amount_max": 95,
        },
        "social_connection",
        "Prânz cu colegii",
        9,
        "2026-06-11T13:05:00+03:00",
    ),
    rule(
        {
            "category": "groceries",
            "weekdays": [7],
            "from": "10:00",
            "to": "12:30",
            "amount_min": 60,
            "amount_max": 420,
        },
        "household_care",
        "Cumpărături pentru părinți",
        7,
        "2026-06-14T11:20:00+03:00",
    ),
    rule(
        {
            "category": "kids",
            "weekdays": [6, 7],
            "from": "10:00",
            "to": "18:30",
            "amount_min": 25,
            "amount_max": 260,
        },
        "household_care",
        "Weekend cu copiii",
        6,
        "2026-06-13T15:40:00+03:00",
    ),
    rule(
        {
            "category": "restaurants",
            "weekdays": [5, 6],
            "from": "18:00",
            "to": "23:00",
            "amount_min": 150,
            "amount_max": 750,
        },
        "social_connection",
        "Ieșit cu prietenii",
        5,
        "2026-06-12T21:10:00+03:00",
        share=0.5,
    ),
    rule(
        {
            "category": "pets",
            "weekdays": [1, 2, 3, 4, 5, 6],
            "from": "10:00",
            "to": "19:00",
            "amount_min": 30,
            "amount_max": 650,
        },
        "household_care",
        "Pentru Bruno",
        4,
        "2026-06-09T17:30:00+03:00",
    ),
    rule(
        {
            "category": "health_pharmacy",
            "weekdays": [1, 2, 3, 4, 5, 6],
            "from": "09:00",
            "to": "20:00",
            "amount_min": 15,
            "amount_max": 150,
        },
        "essential_living",
        "Farmacie pentru copii",
        5,
        "2026-06-10T18:45:00+03:00",
    ),
]


# ── extras.json (the tables the generator doesn't cover) ────────────────────

CATEGORY_RO = {
    "food_delivery": "livrări",
    "restaurants": "restaurante",
    "groceries": "mâncare",
    "kids": "copii",
    "clothing": "haine",
    "fuel": "benzină",
}
MONTH_RO = [
    "ianuarie",
    "februarie",
    "martie",
    "aprilie",
    "mai",
    "iunie",
    "iulie",
    "august",
    "septembrie",
    "octombrie",
    "noiembrie",
    "decembrie",
]


def month_starts(first: date, last: date) -> list[date]:
    out, d = [], first.replace(day=1)
    while d <= last:
        out.append(d)
        d = (d + timedelta(days=32)).replace(day=1)
    return out


def split(total: int, parts: int, rng: random.Random) -> list[int]:
    """`total` in `parts` round amounts (multiples of 50) that add up exactly."""
    base = [total // parts // 50 * 50] * parts
    left = total - sum(base)
    while left > 0:
        i = rng.randrange(parts)
        step = min(50, left)
        base[i] += step
        left -= step
    return base


def transfers(rng: random.Random) -> list[dict[str, Any]]:
    """Monthly transfers after payday; each pot's transfers add up to its `saved`."""
    out = []
    for name, saved, first in [(GOAL_POT[0], GOAL_SAVED, GOAL_POT[1])] + [
        (n, s, f) for n, _, _, s, _, f in POTS
    ]:
        months = month_starts(first, LAST_DAY.replace(day=1))
        for month, amount in zip(months, split(int(saved), len(months), rng), strict=True):
            day = month.replace(day=11)
            if day <= LAST_DAY:
                out.append(
                    {
                        "pot": name,
                        "amount": str(amount),
                        "kind": "manual",
                        "created_at": at(day, 9, rng.randrange(60)),
                    }
                )
    return sorted(out, key=lambda t: (t["created_at"], t["pot"]))


def receivables(rows: list[dict[str, Any]], rng: random.Random) -> list[dict[str, Any]]:
    """Dinners split with friends: most paid back, the last few still open."""
    dinners = [
        r
        for r in rows
        if r["stream"] == "weekend_restaurant"
        and Decimal(r["amount"]) >= 300
        and r["occurred_at"] >= "2024-01-01"
    ]
    friends = ["Ana-Maria", "Mihai și Ioana", "Vlad", "colegii", "Cristina", "Sorin"]
    out = []
    dinners = dinners[-30:]
    for i, row in enumerate(dinners):
        when = datetime.fromisoformat(row["occurred_at"])
        people = rng.choice([2, 2, 3, 4])
        each = (Decimal(row["amount"]) / people).quantize(Decimal("1"))
        owed = each * (people - 1)
        is_open = i >= len(dinners) - 3  # the last three aren't paid back yet
        out.append(
            {
                "amount": str(owed),
                "debtor_label": rng.choice(friends),
                "people_count": people,
                "amount_each": str(each),
                "expected_by": (when.date() + timedelta(days=14)).isoformat(),
                "status": "open" if is_open else "paid",
                "requested_at": None if is_open else (when + timedelta(days=1)).isoformat(),
                "paid_at": None
                if is_open
                else (when + timedelta(days=rng.randint(2, 9))).isoformat(),
                "created_at": (when + timedelta(minutes=20)).isoformat(),
            }
        )
    return out


def life_events() -> list[dict[str, Any]]:
    done = [
        {
            "name": f"Vacanță {place}",
            "date": first.isoformat(),
            "est_cost": booking,
            "type": "trip",
            "status": "done",
        }
        for first, _, place, booking, *_ in VACATIONS
    ]
    planned = [
        ("Tabără Ana", "2026-07-10", "1800", "education"),
        ("Electric Castle", "2026-07-15", "1900", "social"),
        ("Vacanță Corfu", "2026-08-02", "6400", "trip"),
        ("Începutul școlii", "2026-09-14", "1500", "education"),
        ("Ziua lui Luca", "2026-09-14", "900", "social"),
        ("Revizie + RCA", "2026-10-01", "2900", "purchase"),
        ("Crăciun", "2026-12-20", "3000", "gift"),
    ]
    return done + [
        {"name": n, "date": d, "est_cost": c, "type": t, "status": "planned"}
        for n, d, c, t in planned
    ]


def slips(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The weeks delivery + clothes went well over her usual (the last year)."""
    weekly: dict[date, Decimal] = defaultdict(Decimal)
    for r in rows:
        if r["stream"] in ("delivery", "clothes") and r["occurred_at"] >= "2025-06-15":
            d = datetime.fromisoformat(r["occurred_at"]).date()
            weekly[d - timedelta(days=d.weekday())] += Decimal(r["amount"])
    usual = sorted(weekly.values())[len(weekly) // 2]
    return [
        {
            "date": (week + timedelta(days=6)).isoformat(),
            "amount_over": str(total - usual),
            "reason": "Am comandat mâncare de mai multe ori și am luat haine",
            "detail": f"{lei(total)} lei pe livrări și haine într-o săptămână",
            "recurring": total > 2 * usual,
        }
        for week, total in sorted(weekly.items())
        if total > usual * Decimal("1.8")
    ]


ANSWERS = [  # (motivation, answer, reason)
    (5, "Super, am stat bine cu bugetul", "Am gătit acasă toată săptămâna"),
    (4, "Bine, doar o comandă în plus", "Am fost obosită miercuri"),
    (4, "Ok, cu o ieșire cu prietenii", "A fost ziua Cristinei"),
    (3, "Așa și așa, am luat haine pentru copii", "Au crescut din toate"),
    (5, "Foarte bine, am pus și ceva în plus deoparte", "Am primit plata pe freelance"),
    (2, "Grea, s-a stricat mașina de spălat", "Reparația n-a fost planificată"),
    (4, "Bine, weekendul la părinți ne-a ajutat", "Am mâncat la mama"),
]


def reflections(rng: random.Random) -> list[dict[str, Any]]:
    monday = LAST_DAY - timedelta(days=LAST_DAY.weekday())
    out = []
    for i in range(52):
        week = monday - timedelta(weeks=i + 1)
        motivation, answer, reason = rng.choice(ANSWERS)
        out.append(
            {
                "week_start": week.isoformat(),
                "motivation": motivation,
                "answer": answer,
                "reason": reason,
            }
        )
    return sorted(out, key=lambda r: r["week_start"])


def spend(
    rows: list[dict[str, Any]], category: str, first: date, last: date
) -> tuple[Decimal, int]:
    found = [
        Decimal(r["amount"])
        for r in rows
        if r["direction"] == "debit"
        and r["category"] == category
        and first <= datetime.fromisoformat(r["occurred_at"]).date() <= last
    ]
    return sum(found, Decimal(0)), len(found)


def chat(
    rows: list[dict[str, Any]], moves: list[dict[str, Any]], rng: random.Random
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Four months of conversation (messages) and the pushes that opened it (notifications)."""
    messages: list[dict[str, Any]] = []
    notifications: list[dict[str, Any]] = []

    def say(role: str, content: str, when: datetime, **kw: Any) -> None:
        messages.append(
            {
                "role": role,
                "content": content,
                "created_at": when.isoformat(),
                "input_mode": kw.pop("input_mode", "text" if role == "user" else None),
                **kw,
            }
        )

    first = date(2026, 2, 15)
    big = [
        r
        for r in rows
        if r["direction"] == "debit"
        and Decimal(r["amount"]) >= 350
        and r["category"]
        in ("household_goods", "clothing", "kids", "electronics", "gifts", "restaurants")
        and r["occurred_at"] >= first.isoformat()
    ]
    replies = {
        "household_goods": ("Am luat lucruri pentru casă, era nevoie", "Pentru casă"),
        "clothing": ("Haine pentru copii, au crescut", "Pentru copii"),
        "kids": ("Pentru Ana și Luca", "Pentru copii"),
        "electronics": ("S-a stricat tableta Anei", "Necesar"),
        "gifts": ("Cadou pentru ziua cuiva", "Cadou"),
        "restaurants": ("Am ieșit cu prietenii, ne-am împărțit nota", "Cu prietenii"),
    }
    for r in big:
        when = datetime.fromisoformat(r["occurred_at"]) + timedelta(minutes=3)
        merchant = r["merchant_raw"].title()
        question = f"Am văzut {lei(r['amount'])} lei la {merchant}. Pentru ce a fost?"
        text, chip = replies[r["category"]]
        say(
            "assistant",
            question,
            when,
            quick_replies=[chip, "Pentru mine", "Altceva"],
            speak=True,
            speak_text=question,
        )
        notifications.append(
            {
                "type": "agent_message",
                "title": "CashGuard",
                "body": question,
                "read": True,
                "opens_chat": True,
                "created_at": when.isoformat(),
            }
        )
        reply_at = when + timedelta(minutes=rng.randint(2, 90))
        voice = rng.random() < 0.4
        say("user", text, reply_at, input_mode="voice" if voice else "quick_reply")
        say(
            "assistant",
            f"Mulțumesc, am notat: {chip.lower()}.",
            reply_at + timedelta(seconds=9),
            speak=voice,
            speak_text="Mulțumesc, am notat." if voice else None,
        )

    for day in [first + timedelta(days=i) for i in range((LAST_DAY - first).days + 1)]:
        if day.weekday() == 2 and rng.random() < 0.7:  # Wednesdays: "how much on …?"
            category = rng.choice(list(CATEGORY_RO))
            total, n = spend(rows, category, day.replace(day=1), day)
            prev_first = (day.replace(day=1) - timedelta(days=1)).replace(day=1)
            prev_day = min(prev_first.replace(day=28), prev_first + timedelta(days=day.day - 1))
            prev, _ = spend(rows, category, prev_first, prev_day)
            asked = datetime.combine(day, time(20, rng.randrange(60)), tzinfo=BUCHAREST)
            say("user", f"Cât am cheltuit pe {CATEGORY_RO[category]} luna asta?", asked)
            say(
                "assistant",
                f"Din 1 {MONTH_RO[day.month - 1]} până azi ai {lei(total)} lei pe "
                f"{CATEGORY_RO[category]}, în {n} plăți. Luna trecută, în aceeași perioadă, erau "
                f"{lei(prev)} lei.",
                asked + timedelta(seconds=7),
            )
        if day.weekday() == 6:  # Sunday evening: the weekly reflection
            asked = datetime.combine(day, time(19, 30), tzinfo=BUCHAREST)
            question = (
                "Cum a fost săptămâna? De la 1 la 5, cât de motivată te simți pentru bucătărie?"
            )
            say("assistant", question, asked, quick_replies=["5", "4", "3", "2", "1"])
            notifications.append(
                {
                    "type": "agent_message",
                    "title": "Reflecția săptămânii",
                    "body": question,
                    "read": True,
                    "opens_chat": True,
                    "created_at": asked.isoformat(),
                }
            )
            motivation, answer, _ = rng.choice(ANSWERS)
            say("user", f"{motivation}. {answer}", asked + timedelta(minutes=rng.randint(5, 120)))
            say(
                "assistant",
                "Mulțumesc că mi-ai spus, am notat pentru săptămâna asta.",
                asked + timedelta(minutes=125),
            )
        if day.day == 11:  # the day after payday: what went to the pots
            saved = [t for t in moves if t["created_at"][:10] == day.isoformat()]
            if saved:
                total = sum(Decimal(t["amount"]) for t in saved)
                goal_total = sum(
                    Decimal(t["amount"])
                    for t in moves
                    if t["pot"] == GOAL_POT[0] and t["created_at"][:10] <= str(day)
                )
                when = datetime.combine(day, time(9, 30), tzinfo=BUCHAREST)
                body = (
                    f"Am pus deoparte {lei(total)} lei în {len(saved)} pușculițe. Pentru "
                    f"bucătărie ai {lei(goal_total)} din 30.000 de lei."
                )
                say("assistant", body, when)
                notifications.append(
                    {
                        "type": "agent_message",
                        "title": "Economii",
                        "body": body,
                        "read": True,
                        "opens_chat": True,
                        "created_at": when.isoformat(),
                    }
                )
    goal_asked = datetime.combine(LAST_DAY, time(21, 5), tzinfo=BUCHAREST)
    say(
        "user",
        "Mai am șanse să strâng pentru bucătărie până la anul în iunie?",
        goal_asked,
        input_mode="voice",
    )
    say(
        "assistant",
        "Ai strâns 17.400 de lei din 30.000 pentru bucătărie. Mai ai de pus 12.600 de lei "
        "până pe 30 iunie 2027.",
        goal_asked + timedelta(seconds=11),
        speak=True,
        speak_text="Ai strâns cincizeci și opt la sută din bani pentru bucătărie.",
    )
    messages.sort(key=lambda m: m["created_at"])
    notifications.sort(key=lambda n: n["created_at"])
    for n in notifications[-3:]:
        n["read"] = False
    return messages, notifications


# ── writing ──────────────────────────────────────────────────────────────────


def build(folder: Path = FOLDER) -> dict[str, int]:
    """Write every file of Elena's folder; returns the row count of each kind of data."""
    gen = load_generator()
    rng = random.Random(SEED)  # noqa: S311 (seeded demo data, not crypto)
    folder.mkdir(parents=True, exist_ok=True)
    cfg = config(rng)
    (folder / "config.json").write_text(gen.dump(cfg), encoding="utf-8")
    (folder / "facts.json").write_text(gen.dump({"facts": FACTS}), encoding="utf-8")
    (folder / "rules.json").write_text(gen.dump({"rules": RULES}), encoding="utf-8")
    gen.write_persona(folder)
    rows = json.loads((folder / "transactions.json").read_text(encoding="utf-8"))
    moves = transfers(rng)
    messages, notifications = chat(rows, moves, rng)
    extras = {
        "transfers": moves,
        "receivables": receivables(rows, rng),
        "life_events": life_events(),
        "slips": slips(rows),
        "reflections": reflections(rng),
        "messages": messages,
        "notifications": notifications,
    }
    (folder / "extras.json").write_text(gen.dump(extras), encoding="utf-8")
    return {"transactions": len(rows), "facts": len(FACTS), "rules": len(RULES)} | {
        k: len(v) for k, v in extras.items()
    }


if __name__ == "__main__":
    print(f"elena: {build()}")
