from datetime import date, datetime
import json
from pydantic import BaseModel, field_validator
from typing import Optional

VALID_BROKERS = {"mock", "miniqmt", "tonghuashun"}


class AccountCreate(BaseModel):
    name: str
    broker: str
    credentials_plain: str  # JSON string of plain credentials

    @field_validator("broker")
    @classmethod
    def must_be_valid_broker(cls, v: str) -> str:
        if v not in VALID_BROKERS:
            raise ValueError(f"broker must be one of {sorted(VALID_BROKERS)}, got '{v}'")
        return v

    @field_validator("credentials_plain")
    @classmethod
    def must_be_valid_json(cls, v: str) -> str:
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"credentials_plain must be valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ValueError("credentials_plain must be a JSON object")
        return v


class AccountOut(BaseModel):
    id: int
    name: str
    broker: str
    enabled: bool
    circuit_broken: bool
    consecutive_failures: int
    created_at: datetime

    model_config = {"from_attributes": True}


class BondSnapshotOut(BaseModel):
    id: int
    trade_date: date
    bond_code: str
    bond_name: Optional[str]
    market: Optional[str]
    source: Optional[str]
    confirmed: bool

    model_config = {"from_attributes": True}


class SubscriptionOut(BaseModel):
    id: int
    trade_date: date
    bond_code: str
    bond_name: Optional[str]
    account_id: int
    status: str
    error: Optional[str]
    retry_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfigEntryOut(BaseModel):
    key: str
    value: str

    model_config = {"from_attributes": True}


class ConfigEntryCreate(BaseModel):
    value: str
