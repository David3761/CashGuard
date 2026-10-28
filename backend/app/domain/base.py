"""Building blocks shared by `models.py` and `results.py` (kept apart to avoid an import cycle).

- `Frozen`: immutable, unknown fields rejected.
- `Money`: `Decimal`, rounded half-up to 2 dp on input, a JSON **number** in JSON mode
  (`model_dump(mode="json")`), a `Decimal` in Python mode.
- `Score`: a float in [0, 1] (life-fit, anomaly scores, confidences, probabilities).
"""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, PlainSerializer

from app.domain.money import to_money


class Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


def _to_float(value: Decimal) -> float:
    return float(value)


Money = Annotated[
    Decimal,
    AfterValidator(to_money),
    PlainSerializer(_to_float, return_type=float, when_used="json"),
]
PositiveMoney = Annotated[Money, Field(gt=0)]
NonNegativeMoney = Annotated[Money, Field(ge=0)]
Score = Annotated[float, Field(ge=0, le=1)]
Weekday = Annotated[int, Field(ge=1, le=7)]  # ISO: Monday = 1 … Sunday = 7
Month = Annotated[int, Field(ge=1, le=12)]
