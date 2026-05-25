from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.constants import SUPPORTED_RESOLUTIONS


class MarketDataRow(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataResponse(BaseModel):
    symbol: str
    provider: Literal["alpaca"]
    resolution: str
    start_date: date
    stop_date: date
    cache_status: str
    rows: list[MarketDataRow]


class BarsQueryParams(BaseModel):
    start_date: date
    stop_date: date
    resolution: str = Field(description="Bar resolution such as 1m, 5m, 15m, 1h, or 1d")
    feed: Literal["iex", "sip", "otc"] = "iex"
    force_refresh: bool = False

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        if value not in SUPPORTED_RESOLUTIONS:
            supported = ", ".join(SUPPORTED_RESOLUTIONS)
            raise ValueError(f"resolution must be one of: {supported}")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "BarsQueryParams":
        if self.start_date > self.stop_date:
            raise ValueError("start_date must be <= stop_date")
        return self
