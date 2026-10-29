"""bomboe's building-block names, kept as thin aliases over our F2 (the integration's compat layer).

His platform code (B6a schemas, B8 ingest) imports these. Each is the F2 type itself, so the
validation is ours: `Frozen` is `DomainModel` (frozen, unknown fields rejected, `replace()`),
`Money` is `app.domain.money.Money` (half-up to the cent, a JSON number), `Score` is a ratio in
[0, 1] (no NaN / inf / bool).
"""

from typing import Annotated

from pydantic import Field

from app.domain.models import DomainModel, NonNegMoney, Ratio
from app.domain.models import PositiveMoney as PositiveMoney
from app.domain.money import Money as Money

Frozen = DomainModel
NonNegativeMoney = NonNegMoney
Score = Ratio
Weekday = Annotated[int, Field(ge=1, le=7, strict=True)]  # ISO: Monday = 1 … Sunday = 7
Month = Annotated[int, Field(ge=1, le=12, strict=True)]

__all__ = [
    "Frozen",
    "Money",
    "Month",
    "NonNegativeMoney",
    "PositiveMoney",
    "Score",
    "Weekday",
]
