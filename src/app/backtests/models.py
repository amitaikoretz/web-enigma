from __future__ import annotations

from datetime import date, datetime
from math import isnan
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config.models import AnalyzerConfig, BacktestExecutionConfig, BrokerConfig
from app.output.models import BacktestReport
from app.strategies.registry import STRATEGY_REGISTRY, validate_strategy_params


SUPPORTED_RESOLUTIONS = ("1m", "5m", "15m", "1h", "1d")

BacktestJobStatus = Literal["pending", "running", "completed", "failed"]


def _sanitize_strategy_params(params: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, float) and isnan(value):
            continue
        cleaned[key] = value
    return cleaned


class BacktestStrategySelection(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_strategy(self) -> "BacktestStrategySelection":
        if self.name not in STRATEGY_REGISTRY:
            available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
            raise ValueError(f"Unknown strategy '{self.name}'. Available: {available}")
        self.params = validate_strategy_params(self.name, _sanitize_strategy_params(self.params))
        return self


class BacktestCreateRequest(BaseModel):
    start_date: date
    end_date: date
    resolution: str = Field(description="Bar resolution such as 1m, 5m, 15m, 1h, or 1d")
    feed: Literal["iex", "sip", "otc"] = "iex"
    symbols: list[str] = Field(min_length=1)
    strategies: list[BacktestStrategySelection] = Field(min_length=1)
    broker: BrokerConfig | None = None
    analyzers: AnalyzerConfig | None = None
    execution: BacktestExecutionConfig | None = None

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        if value not in SUPPORTED_RESOLUTIONS:
            supported = ", ".join(SUPPORTED_RESOLUTIONS)
            raise ValueError(f"resolution must be one of: {supported}")
        return value

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip().upper()
            if not item:
                raise ValueError("symbols must not contain empty values")
            if item not in normalized:
                normalized.append(item)
        if not normalized:
            raise ValueError("At least one symbol is required")
        return normalized

    @model_validator(mode="after")
    def validate_dates(self) -> "BacktestCreateRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self


class BacktestSelectionSummary(BaseModel):
    start_date: date
    end_date: date
    resolution: str
    feed: Literal["iex", "sip", "otc"]
    symbols: list[str]
    strategies: list[str]


class BacktestListItem(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    status: BacktestJobStatus
    report_status: Literal["success", "partial_failure", "failure"] | None = None
    total_runs: int
    completed_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    selection: BacktestSelectionSummary
    error_message: str | None = None


class BacktestCreateResponse(BaseModel):
    backtest_id: str
    status: BacktestJobStatus
    status_url: str
    detail_url: str


class BacktestStatusResponse(BacktestListItem):
    pass


class BacktestDetailResponse(BaseModel):
    metadata: BacktestListItem
    output_path: str | None = None
    report: BacktestReport | None = None
