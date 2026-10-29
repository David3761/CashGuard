"""RO / EN labels for categories, purposes and beneficiaries (C1.4, arch 9.1, D33).

The app never maps enum values to text itself: `category_label` and `purpose_label` come from
here. One read-only table per enum, chosen by the value's type: values repeat across enums
(`Decision.AUTO == AnnotationSource.AUTO`), so a single mixed table could pick the wrong row.
The purpose labels describe, never judge (no "impuls", no "risipă").
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from app.domain.enums import Beneficiary, Category, Language, Purpose

_Rows = Mapping[str, tuple[str, str]]  # value -> (ro, en)

_CATEGORY: Final[_Rows] = MappingProxyType[str, tuple[str, str]](
    {
        Category.GROCERIES: ("Cumpărături", "Groceries"),
        Category.RESTAURANTS: ("Restaurante", "Restaurants"),
        Category.FOOD_DELIVERY: ("Livrare de mâncare", "Food delivery"),
        Category.TRANSPORT: ("Transport", "Transport"),
        Category.FUEL: ("Carburant", "Fuel"),
        Category.ELECTRONICS: ("Electronice", "Electronics"),
        Category.CLOTHING: ("Haine", "Clothing"),
        Category.SPORT: ("Sport", "Sport"),
        Category.HEALTH_PHARMACY: ("Sănătate și farmacie", "Health & pharmacy"),
        Category.KIDS: ("Copii", "Kids"),
        Category.EDUCATION: ("Educație", "Education"),
        Category.BOOKS: ("Cărți", "Books"),
        Category.ENTERTAINMENT: ("Divertisment", "Entertainment"),
        Category.SUBSCRIPTIONS: ("Abonamente", "Subscriptions"),
        Category.TRAVEL: ("Călătorii", "Travel"),
        Category.HOUSING_RENT: ("Chirie și locuință", "Rent & housing"),
        Category.UTILITIES: ("Utilități", "Utilities"),
        Category.TELECOM: ("Telefon și internet", "Phone & internet"),
        Category.GIFTS: ("Cadouri", "Gifts"),
        Category.PETS: ("Animale de companie", "Pets"),
        Category.HOUSEHOLD_GOODS: ("Casă și gospodărie", "Household goods"),
        Category.PERSONAL_CARE: ("Îngrijire personală", "Personal care"),
        Category.TRANSFERS: ("Transferuri", "Transfers"),
        Category.INCOME: ("Venituri", "Income"),
        Category.SAVINGS: ("Economii", "Savings"),
        Category.OTHER: ("Altele", "Other"),
    }
)
_PURPOSE: Final[_Rows] = MappingProxyType[str, tuple[str, str]](
    {
        Purpose.ESSENTIAL_LIVING: ("Nevoi de bază", "Essentials"),
        Purpose.HOUSEHOLD_CARE: ("Pentru cei dragi", "For your loved ones"),
        Purpose.WORK_TOOL: ("Echipament de lucru", "Work equipment"),
        Purpose.SELF_INVESTMENT: ("Investiție în tine", "Investing in yourself"),
        Purpose.IDENTITY_JOY: ("Pasiuni", "Passions"),
        Purpose.SOCIAL_CONNECTION: ("Socializare", "Social life"),
        Purpose.PLANNED_EVENT: ("Plănuit", "Planned"),
        Purpose.ON_BEHALF_OF_OTHERS: ("Pentru alții", "For others"),
        Purpose.UNPLANNED_DISCRETIONARY: ("Neplanificat", "Unplanned"),
        Purpose.EMERGENCY: ("Urgență", "Emergency"),
        Purpose.UNKNOWN: ("Neprecizat", "Not specified"),
    }
)
_BENEFICIARY: Final[_Rows] = MappingProxyType[str, tuple[str, str]](
    {
        Beneficiary.SELF: ("Pentru tine", "For you"),
        Beneficiary.HOUSEHOLD: ("Pentru cei de acasă", "For your household"),
        Beneficiary.SHARED: ("Împărțit", "Shared"),
        Beneficiary.OTHERS: ("Pentru alții", "For others"),
        Beneficiary.EMPLOYER: ("Pentru angajator", "For your employer"),
    }
)
_TABLES: Final[Mapping[type[StrEnum], _Rows]] = MappingProxyType[type[StrEnum], _Rows](
    {Category: _CATEGORY, Purpose: _PURPOSE, Beneficiary: _BENEFICIARY}
)


def label(value: Category | Purpose | Beneficiary, lang: str) -> str:
    """The localised label: `label(Category.GROCERIES, "ro") == "Cumpărături"`. `lang` is a
    `Language` or its value; anything else → ValueError. Only these three enums → TypeError
    otherwise (convert a DB string with `Category(value)` first)."""
    try:
        language = Language(lang)
    except ValueError:
        raise ValueError(f"unsupported language {lang!r}: expected 'ro' or 'en'") from None
    table = _TABLES.get(type(value))
    if table is None:
        raise TypeError(
            f"label() takes a Category, Purpose or Beneficiary, not {type(value).__name__}"
        )
    ro, en = table[value]
    return ro if language is Language.RO else en
