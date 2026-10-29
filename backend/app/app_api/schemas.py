"""The app API's JSON shapes (API_SPEC.md): snake_case, money in integer bani, UTC `Z` times."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr, field_validator

from app.app_api.mapping import Sender, TxType
from app.db.models import DevicePlatform

FCM_TOKEN_MAX = 512


class BalanceOut(BaseModel):
    balance: StrictInt
    currency: Literal["RON"] = "RON"


class TransactionOut(BaseModel):
    id: StrictInt = Field(gt=0)
    title: StrictStr = Field(min_length=1)
    amount: StrictInt
    type: TxType
    created_at: StrictStr


class TransactionsOut(BaseModel):
    transactions: list[TransactionOut]


class DeviceIn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    fcm_token: StrictStr = Field(min_length=1, max_length=FCM_TOKEN_MAX)
    platform: DevicePlatform

    @field_validator("fcm_token", mode="before")
    @classmethod
    def _strip(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class DeviceOut(BaseModel):
    fcm_token: str
    platform: DevicePlatform


class Empty(BaseModel):
    """`{}`: the app parses every response as a JSON object."""


class MessageOut(BaseModel):
    id: StrictInt = Field(gt=0)
    text: StrictStr
    sender: Sender
    created_at: StrictStr


class MessagesOut(BaseModel):
    messages: list[MessageOut]


class MessageIn(BaseModel):
    """Length and blankness are checked by the route, so the app gets a friendly message."""

    model_config = ConfigDict(extra="ignore")

    text: StrictStr
