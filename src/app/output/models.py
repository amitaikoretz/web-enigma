from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RunError(BaseModel):
    type: str
    message: str


class OrderRecord(BaseModel):
    datetime: str | None = None
    status: str
    is_buy: bool
    size: float
    price: float
    value: float
    commission: float


class TradeRecord(BaseModel):
    datetime: str | None = None
    size: float
    price: float
    value: float
    pnl: float
    pnlcomm: float


class EquityPoint(BaseModel):
    datetime: str
    value: float


class RunSummary(BaseModel):
    start_value: float
    end_value: float
    return_pct: float
    max_drawdown_pct: float | None = None
    sharpe_ratio: float | None = None
    total_trades: int = 0
    won_trades: int = 0
    lost_trades: int = 0


class RunResult(BaseModel):
    run_id: str
    name: str | None = None
    status: Literal["success", "failed"]
    strategy: str
    data_source: str
    summary: RunSummary | None = None
    analyzers: dict[str, Any] = Field(default_factory=dict)
    orders: list[OrderRecord] = Field(default_factory=list)
    trades: list[TradeRecord] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    error: RunError | None = None


class BacktestReport(BaseModel):
    generated_at: datetime
    app_version: str
    config_sha256: str
    input_config_path: str | None = None
    input_config: dict[str, Any] = Field(default_factory=dict)
    total_runs: int
    successful_runs: int
    failed_runs: int
    status: Literal["success", "partial_failure", "failure"]
    results: list[RunResult]
