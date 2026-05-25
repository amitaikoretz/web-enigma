from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

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


class TradingContractUpdate(BaseModel):
    symbol: str | None = Field(default=None, min_length=1)
    strategy: str | None = None
    strategy_params: dict[str, Any] | None = None
    start_datetime: datetime | None = None
    end_datetime: datetime | None = None
    maximum_trade_size: float | None = Field(default=None, gt=0)
    total_invested: float | None = Field(default=None, ge=0)

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @field_validator("start_datetime", "end_datetime")
    @classmethod
    def validate_timezone_aware(cls, value: datetime | None, info) -> datetime | None:
        if value is None:
            return value
        return _ensure_timezone_aware(value, info.field_name)


class TradingContractResponse(BaseModel):
    id: UUID
    symbol: str
    strategy: str
    strategy_params: dict[str, Any]
    start_datetime: datetime
    end_datetime: datetime
    maximum_trade_size: float
    total_invested: float
    revision: int
    deleted_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, contract: TradingContract) -> "TradingContractResponse":
        created_at = contract.created_at
        if created_at.tzinfo is None or created_at.utcoffset() is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        deleted_at = contract.deleted_at
        if deleted_at is not None and (deleted_at.tzinfo is None or deleted_at.utcoffset() is None):
            deleted_at = deleted_at.replace(tzinfo=timezone.utc)
        return cls(
            id=contract.id,
            symbol=contract.symbol,
            strategy=contract.strategy,
            strategy_params=contract.strategy_params or {},
            start_datetime=contract.start_datetime,
            end_datetime=contract.end_datetime,
            maximum_trade_size=float(contract.maximum_trade_size),
            total_invested=float(contract.total_invested),
            revision=int(contract.revision),
            deleted_at=deleted_at,
            created_at=created_at,
        )


class TradingContractListQuery(BaseModel):
    symbol: str | None = None
    strategy: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized


class TradingContractActiveQuery(TradingContractListQuery):
    active_at: datetime | None = None

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


def apply_contract_update(record: TradingContract, payload: TradingContractUpdate) -> None:
    if payload.symbol is not None:
        record.symbol = payload.symbol
    if payload.strategy is not None:
        record.strategy = payload.strategy
    if payload.strategy_params is not None:
        record.strategy_params = payload.strategy_params
    if payload.start_datetime is not None:
        record.start_datetime = payload.start_datetime
    if payload.end_datetime is not None:
        record.end_datetime = payload.end_datetime
    if payload.maximum_trade_size is not None:
        record.maximum_trade_size = Decimal(str(payload.maximum_trade_size))
    if payload.total_invested is not None:
        record.total_invested = Decimal(str(payload.total_invested))

    if record.start_datetime >= record.end_datetime:
        raise ValueError("start_datetime must be < end_datetime")
    if record.strategy not in STRATEGY_REGISTRY:
        available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
        raise ValueError(f"Unknown strategy '{record.strategy}'. Available: {available}")
    record.strategy_params = validate_strategy_params(record.strategy, record.strategy_params or {})
    record.revision = int(record.revision) + 1


def not_deleted_contracts_query() -> Select[tuple[TradingContract]]:
    return select(TradingContract).where(TradingContract.deleted_at.is_(None))


def active_contracts_query(
    *,
    active_at: datetime,
    symbol: str | None = None,
    strategy: str | None = None,
) -> Select[tuple[TradingContract]]:
    query = (
        not_deleted_contracts_query()
        .where(TradingContract.start_datetime <= active_at)
        .where(TradingContract.end_datetime > active_at)
        .order_by(TradingContract.start_datetime.asc())
    )
    if symbol is not None:
        query = query.where(TradingContract.symbol == symbol)
    if strategy is not None:
        query = query.where(TradingContract.strategy == strategy)
    return query


def load_active_contracts(
    session: Session,
    *,
    active_at: datetime | None = None,
    symbol: str | None = None,
    strategy: str | None = None,
) -> list[TradingContract]:
    resolved_active_at = active_at or datetime.now(timezone.utc)
    query = active_contracts_query(
        active_at=resolved_active_at,
        symbol=symbol,
        strategy=strategy,
    )
    return list(session.execute(query).scalars().all())


def get_live_contract_or_none(session: Session, contract_id: UUID) -> TradingContract | None:
    return session.execute(
        select(TradingContract).where(
            TradingContract.id == contract_id,
            TradingContract.deleted_at.is_(None),
        )
    ).scalar_one_or_none()
