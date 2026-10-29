"""Domain models (F2): the typed, immutable views every pure core uses (work-breakdown F2).

Every model is a `DomainModel`:
- **frozen**: assigning a field raises, so no value can skip its validator (e.g. `Money`'s
  rounding). Change a model with `replace(**changes)`, which validates like a new model;
  `model_copy(update=...)` doesn't, so don't use it.
- **extra="forbid"**: an unknown key (e.g. a smuggled `user_id`) is an error.
- sequences are tuples (deeply immutable); maps are typed `Mapping` (read-only for mypy).
- `model_validate_json` reads every number exactly and rejects duplicate keys
  (`money.parse_json`): pydantic's own JSON parser reads numbers as floats first.

Scores and probabilities are `float` (`Ratio`, 0-1); money is `Money` and anything multiplied with
money is a `Factor` (both `Decimal`, both JSON numbers): `Decimal * float` raises (plan Q1).
Timestamps are tz-aware (`Timestamp`: never Unix-time numbers). There's no `user_id` on a view
(the services scope every query, and `UserContext` carries the one user id).
"""

import re
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Self

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    ValidationError,
    WithJsonSchema,
    model_validator,
)
from pydantic.config import ExtraValues
from pydantic_core import InitErrorDetails

from app.domain.enums import AnnotationSource, Beneficiary, Category, Decision, Direction, Purpose
from app.domain.money import Money, decimal_to_json, parse_json, to_decimal

# ── the base model ───────────────────────────────────────────────────────────────────────────


class DomainModel(BaseModel):
    """Frozen, no unknown keys, changed only through `replace`, JSON read exactly.

    pydantic's bypasses are closed: `model_copy(update=...)` re-validates, `model_construct`
    raises, and `extra=` overrides of `extra="forbid"` are refused.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        validate_by_name=True,
        validate_by_alias=True,
        serialize_by_alias=True,
    )

    def replace(self, **changes: object) -> Self:
        """A copy with `changes`, validated like a new model (unknown fields are errors)."""
        return self.model_validate({**self.model_dump(by_alias=False), **changes})

    def model_copy(self, *, update: Mapping[str, Any] | None = None, deep: bool = False) -> Self:
        """A validated copy (pydantic's skips validation). `deep` is moot: models are frozen."""
        return self.replace(**(update or {}))

    @classmethod
    def model_construct(  # type: ignore[override]  # the pydantic plugin types it per model
        cls, _fields_set: set[str] | None = None, **values: Any
    ) -> Self:
        """Refused: it skips validation. Use `model_validate`."""
        raise TypeError(f"{cls.__name__}.model_construct skips validation: use model_validate")

    @classmethod
    def model_validate(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        from_attributes: bool | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """pydantic's, without the `extra=` override (it would undo `extra="forbid"`)."""
        _refuse_extra(cls, extra)
        return super().model_validate(
            obj,
            strict=strict,
            from_attributes=from_attributes,
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )

    @classmethod
    def model_validate_strings(
        cls,
        obj: Any,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        _refuse_extra(cls, extra)
        return super().model_validate_strings(
            obj, strict=strict, context=context, by_alias=by_alias, by_name=by_name
        )

    @classmethod
    def model_validate_json(
        cls,
        json_data: str | bytes | bytearray,
        *,
        strict: bool | None = None,
        extra: ExtraValues | None = None,
        context: Any | None = None,
        by_alias: bool | None = None,
        by_name: bool | None = None,
    ) -> Self:
        """Numbers read exactly; duplicate keys, NaN, bad JSON and deep nesting are a
        `ValidationError` (json_invalid), like pydantic's own parse errors."""
        _refuse_extra(cls, extra)
        if strict:  # it would mean python-mode strictness (e.g. no date strings): refuse it
            raise TypeError("DomainModel.model_validate_json has no strict mode")
        return cls.model_validate(
            parse_json_or_error(json_data, cls.__name__),
            context=context,
            by_alias=by_alias,
            by_name=by_name,
        )


def _refuse_extra(cls: type[BaseModel], extra: ExtraValues | None) -> None:
    if extra is not None:
        raise TypeError(f"{cls.__name__}: extra= is refused (domain models forbid unknown keys)")


def parse_json_or_error(data: str | bytes | bytearray, title: str) -> object:
    """`money.parse_json`, with every parse failure turned into a pydantic `ValidationError`."""
    try:
        return parse_json(data)
    except (ValueError, RecursionError) as error:
        detail = InitErrorDetails(
            type="json_invalid", loc=(), input=data, ctx={"error": str(error)}
        )
        raise ValidationError.from_exception_data(title, [detail], input_type="json") from None


# ── shared field types ───────────────────────────────────────────────────────────────────────


def _not_bool(value: object) -> object:
    if isinstance(value, bool):  # True would silently be 1.0
        raise ValueError("a bool is not a number")
    return value


_ISO_TIMESTAMP = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(:[0-9]{2}(\.[0-9]{1,6})?)?(Z|[+-][0-9]{2}:[0-9]{2})"
)


def _timestamp_input(value: object) -> object:
    # pydantic's lax datetime reads ints, floats and numeric strings as Unix time (20260615 ->
    # 1970-08-23): only datetimes and ISO-8601 strings with an offset are timestamps here.
    if isinstance(value, datetime) or (isinstance(value, str) and _ISO_TIMESTAMP.fullmatch(value)):
        return value
    raise ValueError("a timestamp is an aware datetime or ISO-8601 with an offset")


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


def _unique(values: tuple[str, ...]) -> tuple[str, ...]:
    if len(set(values)) != len(values):
        raise ValueError("values must be unique")
    return values


Id = Annotated[int, Field(gt=0, le=2**63 - 1, strict=True)]
"""A database id: a positive BIGINT (strict: not True, not "5")."""
MerchantId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(_[a-z0-9]+)*$", max_length=40)]
"""A merchant slug, e.g. "mega_image" (D47; C1's data/merchants.json)."""
Mcc = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")]
"""An ISO 18245 merchant category code: 4 digits as text (0742 keeps its 0)."""
Timestamp = Annotated[AwareDatetime, BeforeValidator(_timestamp_input)]
"""A tz-aware instant: an aware datetime or an ISO-8601 string with an offset (never Unix time)."""
Text80 = Annotated[str, StringConstraints(min_length=1, max_length=80), AfterValidator(_not_blank)]
Text200 = Annotated[
    str, StringConstraints(min_length=1, max_length=200), AfterValidator(_not_blank)
]
Text300 = Annotated[
    str, StringConstraints(min_length=1, max_length=300), AfterValidator(_not_blank)
]
Text500 = Annotated[
    str, StringConstraints(min_length=1, max_length=500), AfterValidator(_not_blank)
]
"""Texts kept exactly as given: at most N characters, not only whitespace (they reach prompts)."""
PositiveMoney = Annotated[Money, Field(gt=0)]
NonNegMoney = Annotated[Money, Field(ge=0)]
Ratio = Annotated[float, BeforeValidator(_not_bool), Field(ge=0, le=1, allow_inf_nan=False)]
"""A score, confidence or probability in [0, 1]."""
Factor = Annotated[
    Decimal,
    BeforeValidator(to_decimal),
    PlainSerializer(decimal_to_json, return_type=float, when_used="json"),
    WithJsonSchema({"type": "number"}),
]
"""An exact Decimal that multiplies money (a multiplier, a household scale); a JSON number."""


# ── transactions & the merchant catalogue ───────────────────────────────────────────────────


class Item(DomainModel):
    """A receipt line (arch 4.4 `transactions.items`, D32)."""

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    qty: Annotated[int, Field(ge=1, strict=True)] = 1
    amount: NonNegMoney | None = None


class TxView(DomainModel):
    """A transaction as the cores read it (arch 4.1 + 4.4 columns; §15 calls it `Transaction`).

    `category` is None only before the first evaluation of a transaction that came without a
    script category (arch F2, Q8); every resolved one has it.
    """

    id: Id
    occurred_at: Timestamp
    merchant_raw: Text200  # B8's ingest limit
    merchant: Text80 | None = None  # a canonical name (Merchant's limit)
    merchant_id: MerchantId | None = None
    mcc: Mcc | None = None
    category: Category | None = None
    direction: Direction
    amount: PositiveMoney
    effective_amount: NonNegMoney
    items: tuple[Item, ...] | None = None  # None = no item data (D32), () = an empty receipt
    description: Text500 | None = None
    purpose: Purpose | None = None
    beneficiary: Beneficiary | None = None
    annotation_source: AnnotationSource | None = None
    annotation_confidence: Ratio | None = None
    explanation: Text300 | None = None  # the "because"
    decision: Decision | None = None
    life_fit: Ratio | None = None
    anomaly_score: Ratio | None = None
    unexplained: Ratio | None = None
    matched_fact_id: Id | None = None
    matched_rule_id: Id | None = None
    pot_id: Id | None = None
    receivable_id: Id | None = None

    @model_validator(mode="after")
    def _effective_within_amount(self) -> Self:
        if self.effective_amount > self.amount:
            raise ValueError(
                f"effective_amount {self.effective_amount} must not exceed amount {self.amount}"
            )
        return self


class Merchant(DomainModel):
    """A merchant of the catalogue (arch 4.4 `merchants`; C1's data/merchants.json)."""

    id: MerchantId
    canonical_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)
    ]
    aliases: Annotated[
        tuple[Annotated[str, StringConstraints(min_length=3, max_length=60)], ...],
        Field(min_length=1),
        AfterValidator(_unique),
    ]
    category: Category
    mcc: Mcc
    typical_basket: PositiveMoney
    multi_category: bool = False
