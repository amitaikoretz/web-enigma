from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.api.constants import SUPPORTED_RESOLUTIONS
from app.config.models import BrokerConfig
from app.output.models import OrderRecord, RunError, RunSummary, TradeRecord

from .market_data import MarketDataRow


class BacktestRunRequest(BaseModel):
    config_text: str = Field(min_length=1)
    format: Literal["json", "yaml"]


class BacktestRunResponse(BaseModel):
    output_path: str
    status: Literal["success", "partial_failure", "failure"]
    total_runs: int
    successful_runs: int
    failed_runs: int


class SingleDayBacktestRequest(BaseModel):
    symbol: str = Field(min_length=1)
    date: date
    resolution: str = Field(description="Bar resolution such as 1m, 5m, 15m, 1h, or 1d")
    feed: Literal["iex", "sip", "otc"] = "iex"
    strategy: str
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    broker: BrokerConfig | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        if value not in SUPPORTED_RESOLUTIONS:
            supported = ", ".join(SUPPORTED_RESOLUTIONS)
            raise ValueError(f"resolution must be one of: {supported}")
        return value


class SingleDayBacktestResult(BaseModel):
    status: Literal["success", "failed"]
    summary: RunSummary | None = None
    orders: list[OrderRecord] = Field(default_factory=list)
    trades: list[TradeRecord] = Field(default_factory=list)
    error: RunError | None = None


class SingleDayBacktestResponse(BaseModel):
    symbol: str
    date: date
    resolution: str
    cache_status: str
    bars: list[MarketDataRow]
    backtest: SingleDayBacktestResult
