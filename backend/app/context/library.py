"""The signature library and `signatures_for_fact` (C4; arch 5.3.3).

**Library first.** `data/signature_library.json` holds ~45 hand-written entries. An entry matches a
fact of one of its `types`:
- by **synonyms**: the fact's key text (an occupation's title, an activity's name…) is folded and
  tokenised like merchant text (C2's `tokens`), and a synonym matches when its tokens appear as a
  contiguous run ("analist sportiv la o televiziune" contains "analist sportiv");
- by **role + age band** for household members (a child of 7 → school supplies + 1 Iunie);
- by **any value** (any pet, any vehicle).
Priority entries only match their `levels` (a "reduce" priority protects nothing). Entries with
`window_from_fact` take the fact's months / date / weekdays as their time window (a trip in August
explains travel in August). Library signatures get `origin = library`.

**Claude's signatures** (`llm_signatures`, from `add_life_fact`) are validated with F2's
`Signature` after dropping unknown fields; `origin = llm`, strength capped at 0.9. Dropped (and
logged by index and reason only, never the content): non-objects, invalid ones (e.g. purpose
"good_purchase", amount_min > amount_max), **anything health / pharmacy** (sensitive, arch 4.5),
household scaling (E6's job, D50) and duplicates. **The library wins** on the same
(effect, category).

The household **multiplier** is not here: E6 computes it from the facts (per child, D50).
"""

import logging
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Final, Self

from pydantic import Field, StrictBool, ValidationError, field_validator, model_validator

from app.context.normalize import normalize, tokens
from app.domain.enums import (
    HOUSEHOLD_SCALED_CATEGORIES,
    Category,
    FactType,
    HouseholdRole,
    PriorityLevel,
    Purpose,
    SignatureEffect,
    SignatureOrigin,
)
from app.domain.models import (
    DomainModel,
    HouseholdMemberValue,
    LifeEventValue,
    LifeFact,
    LifeFactDraft,
    PriorityValue,
    RhythmValue,
    Signature,
    SocialPatternValue,
    TimeWindow,
)
from app.domain.money import parse_json

logger = logging.getLogger(__name__)

LIBRARY_FILE: Final = Path(__file__).resolve().parents[2] / "data" / "signature_library.json"
MAX_LLM_STRENGTH: Final = 0.9
MAX_LLM_SIGNATURES: Final = 8
LLM_FIELDS: Final = frozenset(
    {
        "effect", "category", "merchant_hints", "item_keywords", "amount_min", "amount_max",
        "multiplier", "time_window", "expected_date", "expected_amount",
        "replacement_cycle_days", "purpose", "strength",
    }
)  # fmt: skip
"""What Claude may set; anything else (id, fact_id, origin, active, unknown keys) is dropped."""
HEALTH_WORDS: Final = frozenset(
    {
        "farmacie", "farmacia", "pharmacy", "medicament", "medicamente", "medicine", "medication",
        "pastile", "tratament", "treatment", "medic", "doctor", "clinica", "clinic", "spital",
        "hospital", "analize", "sanatate", "health", "terapie", "therapy", "psiholog",
        "psihoterapie", "dentist", "stomatolog", "vitamine", "suplimente",
    }
)  # fmt: skip
"""Folded tokens that make a Claude signature health-related (dropped: sensitive, arch 4.5)."""
GENERIC_PROTECT_STRENGTH: Final = 0.8
_NOT_PROTECTABLE: Final = frozenset(
    {Category.HEALTH_PHARMACY, Category.TRANSFERS, Category.INCOME, Category.SAVINGS}
)

_KEY_FIELD: Final[dict[FactType, str]] = {
    FactType.OCCUPATION: "title",
    FactType.EMPLOYMENT: "kind",
    FactType.PET: "species",
    FactType.VEHICLE: "kind",
    FactType.COMMUTE: "mode",
    FactType.ACTIVITY: "name",
    FactType.SOCIAL_PATTERN: "name",
    FactType.LIFE_EVENT: "name",
    FactType.RHYTHM: "name",
    FactType.PRIORITY: "category",
    FactType.CUSTOM: "description",
    FactType.HOUSING: "kind",
    FactType.CITY: "name",
    FactType.INCOME_PATTERN: "note",
}
"""The value field whose text is matched against an entry's synonyms."""


class LibraryEntry(DomainModel):
    """One entry of data/signature_library.json."""

    key: Annotated[str, Field(pattern=r"^[a-z0-9]+(_[a-z0-9]+)*$")]
    types: Annotated[tuple[FactType, ...], Field(min_length=1)]
    synonyms: tuple[str, ...] = ()
    any_value: StrictBool = False
    role: HouseholdRole | None = None
    age_min: int | None = None
    age_max: int | None = None
    levels: tuple[PriorityLevel, ...] = ()
    window_from_fact: StrictBool = False
    signatures: Annotated[tuple[Signature, ...], Field(min_length=1)]

    @field_validator("signatures", mode="before")
    @classmethod
    def _library_origin(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        return [
            {**item, "origin": SignatureOrigin.LIBRARY} if isinstance(item, dict) else item
            for item in value
        ]

    @model_validator(mode="after")
    def _one_way_to_match(self) -> Self:
        ways = sum((bool(self.synonyms), self.any_value, self.role is not None))
        if ways != 1:
            raise ValueError(f"{self.key}: match by exactly one of synonyms, any_value, role")
        return self

    def synonym_tokens(self) -> tuple[tuple[str, ...], ...]:
        return tuple(tokens(synonym) for synonym in self.synonyms)


@cache
def load_library() -> tuple[LibraryEntry, ...]:
    """The library, read strictly once (numbers as Decimal, no duplicate keys)."""
    data = parse_json(LIBRARY_FILE.read_bytes())
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError(f"{LIBRARY_FILE.name}: expected {{'entries': [...]}}")
    return tuple(LibraryEntry.model_validate(entry) for entry in data["entries"])


def _contains(words: tuple[str, ...], part: tuple[str, ...]) -> bool:
    size = len(part)
    return size > 0 and any(words[i : i + size] == part for i in range(len(words) - size + 1))


def _matches(entry: LibraryEntry, fact: LifeFactDraft, words: tuple[str, ...]) -> bool:
    if fact.type not in entry.types:
        return False
    value = fact.value
    if isinstance(value, PriorityValue) and entry.levels and value.priority not in entry.levels:
        return False
    if entry.role is not None:
        if not isinstance(value, HouseholdMemberValue) or value.role is not entry.role:
            return False
        if value.age is None:
            return entry.age_min is None and entry.age_max is None
        low = entry.age_min if entry.age_min is not None else 0
        high = entry.age_max if entry.age_max is not None else 120
        return low <= value.age <= high
    if entry.any_value:
        return True
    return any(_contains(words, synonym) for synonym in entry.synonym_tokens())


def _fact_window(fact: LifeFactDraft) -> TimeWindow | None:
    value = fact.value
    if isinstance(value, LifeEventValue):
        months = value.months or ((value.date.month,) if value.date else ())
        return TimeWindow(months=months) if months else None
    if isinstance(value, SocialPatternValue | RhythmValue) and value.weekdays:
        return TimeWindow(weekdays=value.weekdays)
    return None


def _fact_id(fact: LifeFactDraft) -> int | None:
    return fact.id if isinstance(fact, LifeFact) else None


def _generic_protect(fact: LifeFactDraft) -> Signature | None:
    """A protected priority whose text is itself a category ("food_delivery", "travel")."""
    value = fact.value
    if not isinstance(value, PriorityValue) or value.priority is not PriorityLevel.PROTECTED:
        return None
    try:
        category = Category("_".join(tokens(value.category)))
    except ValueError:
        return None
    if category in _NOT_PROTECTABLE:
        return None
    return Signature(
        fact_id=_fact_id(fact),
        effect=SignatureEffect.PROTECTS,
        category=category,
        purpose=Purpose.IDENTITY_JOY,
        strength=GENERIC_PROTECT_STRENGTH,
        origin=SignatureOrigin.LIBRARY,
    )


def library_signatures(fact: LifeFactDraft) -> list[Signature]:
    """The library's signatures for `fact`: one per (effect, category), the strongest kept."""
    field = _KEY_FIELD.get(fact.type)
    text = getattr(fact.value, field, None) if field else None
    words = tokens(text) if isinstance(text, str) else ()
    window = _fact_window(fact)
    best: dict[tuple[SignatureEffect, Category | None], Signature] = {}
    for entry in load_library():
        if not _matches(entry, fact, words):
            continue
        for template in entry.signatures:
            changes: dict[str, Any] = {"fact_id": _fact_id(fact)}
            if entry.window_from_fact and window is not None:
                changes["time_window"] = window
            signature = template.replace(**changes)
            key = (signature.effect, signature.category)
            if key not in best or signature.strength > best[key].strength:
                best[key] = signature
    if not best:
        generic = _generic_protect(fact)
        if generic is not None:
            best[(generic.effect, generic.category)] = generic
    return list(best.values())


def _drop(index: int, reason: str, fact: LifeFactDraft) -> None:
    # Index + reason only: a dropped signature may carry health details (never logged).
    logger.warning(
        "llm signature dropped",
        extra={"index": index, "reason": reason, "fact_type": str(fact.type)},
    )


def _is_health(signature: Signature) -> bool:
    if signature.category is Category.HEALTH_PHARMACY:
        return True
    for hint in signature.merchant_hints:
        if normalize(hint).category is Category.HEALTH_PHARMACY:
            return True
    texts = (*signature.merchant_hints, *signature.item_keywords)
    return any(HEALTH_WORDS & set(tokens(text)) for text in texts)


def _raw_is_health(raw: dict[Any, Any]) -> bool:
    return raw.get("category") == Category.HEALTH_PHARMACY.value


def llm_signatures_checked(
    fact: LifeFactDraft, raw_signatures: object, taken: set[tuple[SignatureEffect, Category | None]]
) -> list[Signature]:
    """Claude's signatures for `fact`, validated and filtered (see the module docstring)."""
    if raw_signatures is None:
        return []
    if not isinstance(raw_signatures, list):
        _drop(-1, "not a list", fact)
        return []
    kept: list[Signature] = []
    for index, raw in enumerate(raw_signatures):
        if len(kept) >= MAX_LLM_SIGNATURES:
            _drop(index, "too many", fact)
            continue
        if not isinstance(raw, dict):
            _drop(index, "not an object", fact)
            continue
        if _raw_is_health(raw):
            _drop(index, "health (sensitive)", fact)
            continue
        fields = {key: value for key, value in raw.items() if key in LLM_FIELDS}
        try:
            signature = Signature.model_validate(
                {**fields, "fact_id": _fact_id(fact), "origin": SignatureOrigin.LLM}
            )
        except ValidationError:
            _drop(index, "invalid", fact)
            continue
        if _is_health(signature):
            _drop(index, "health (sensitive)", fact)
            continue
        if (
            signature.effect is SignatureEffect.SCALES_BASELINE
            and signature.category in HOUSEHOLD_SCALED_CATEGORIES
        ):
            _drop(index, "household scaling is E6's", fact)
            continue
        key = (signature.effect, signature.category)
        if key in taken:
            _drop(index, "duplicate (the library wins)", fact)
            continue
        taken.add(key)
        kept.append(signature.replace(strength=min(signature.strength, MAX_LLM_STRENGTH)))
    return kept


def signatures_for_fact(
    fact: LifeFactDraft, llm_signatures: list[Any] | None = None
) -> list[Signature]:
    """What `fact` predicts about spending: the library's signatures, then Claude's valid ones
    (the library wins on the same effect + category). An unknown fact with none → []."""
    library = library_signatures(fact)
    taken = {(signature.effect, signature.category) for signature in library}
    return library + llm_signatures_checked(fact, llm_signatures, taken)
