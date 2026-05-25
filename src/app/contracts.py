from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.db.models import TradingContract
from app.strategies.registry import STRATEGY_REGISTRY, validate_strategy_params


def _ensure_timezone_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include timezone information")
    return value


class TradingContractCreate(BaseModel):
    symbol: str = Field(min_length=1)
    strategy: str
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    start_datetime: datetime
    end_datetime: datetime
    maximum_trade_size: float = Field(gt=0)
    total_invested: float = Field(ge=0)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def validate_timezone_aware(cls, value: datetime, info) -> datetime:
        return _ensure_timezone_aware(value, info.field_name)

    @model_validator(mode="after")
    def validate_contract(self) -> "TradingContractCreate":
        if self.start_datetime >= self.end_datetime:
            raise ValueError("start_datetime must be < end_datetime")
        if self.strategy not in STRATEGY_REGISTRY:
            available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
            raise ValueError(f"Unknown strategy '{self.strategy}'. Available: {available}")
        self.strategy_params = validate_strategy_params(self.strategy, self.strategy_params)
        return self


class TradingContractResponse(BaseModel):
    id: UUID
    symbol: str
    strategy: str
    strategy_params: dict[str, Any]
    start_datetime: datetime
    end_datetime: datetime
    maximum_trade_size: float
    total_invested: float
    created_at: datetime

    @classmethod
    def from_model(cls, contract: TradingContract) -> "TradingContractResponse":
        created_at = contract.created_at
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return cls(
            id=contract.id,
            symbol=contract.symbol,
            strategy=contract.strategy,
            strategy_params=contract.strategy_params or {},
            start_datetime=contract.start_datetime,
            end_datetime=contract.end_datetime,
            maximum_trade_size=float(contract.maximum_trade_size),
            total_invested=float(contract.total_invested),
            created_at=created_at,
        )


class TradingContractActiveQuery(BaseModel):
    symbol: str | None = None
    strategy: str | None = None
    active_at: datetime | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @field_validator("active_at")
    @classmethod
    def validate_active_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        return _ensure_timezone_aware(value, "active_at")


def to_contract_record(payload: TradingContractCreate) -> TradingContract:
    return TradingContract(
        symbol=payload.symbol,
        strategy=payload.strategy,
        strategy_params=payload.strategy_params,
        start_datetime=payload.start_datetime,
        end_datetime=payload.end_datetime,
        maximum_trade_size=Decimal(str(payload.maximum_trade_size)),
        total_invested=Decimal(str(payload.total_invested)),
    )
