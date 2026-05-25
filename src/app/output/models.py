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
    reason: str | None = None
    entry_datetime: str | None = None
    hold_minutes: float | None = None
    hold_bars: int | None = None
    regime_label: str | None = None


class RejectionRecord(BaseModel):
    datetime: str | None = None
    symbol: str | None = None
    reason: str | None = None


class EquityPoint(BaseModel):
    datetime: str
    value: float


class HistogramBin(BaseModel):
    start: float
    end: float
    count: int
    label: str | None = None


class TradeDistribution(BaseModel):
    hold_time_bins: list[HistogramBin] = Field(default_factory=list)
    hold_time_unit: Literal["minutes", "bars"] = "minutes"
    size_bins: list[HistogramBin] = Field(default_factory=list)
    size_value_bins: list[HistogramBin] | None = None


class TradeDiagnostics(BaseModel):
    net_pnl: float = 0.0
    gross_pnl: float = 0.0
    total_commission: float = 0.0
    commission_pct_of_gross: float | None = None
    profit_factor: float | None = None
    expectancy: float | None = None
    avg_win: float | None = None
    avg_loss: float | None = None
    payoff_ratio: float | None = None
    win_rate_pct: float | None = None
    median_hold_minutes: float | None = None
    mean_hold_minutes: float | None = None
    best_trade_pnl: float | None = None
    worst_trade_pnl: float | None = None
    exit_reason_counts: dict[str, int] = Field(default_factory=dict)
    exit_reason_pnl: dict[str, float] = Field(default_factory=dict)
    dominant_exit_reason: str | None = None
    distributions: TradeDistribution | None = None


class FilterDiagnostics(BaseModel):
    rejection_counts: dict[str, int] = Field(default_factory=dict)
    total_rejections: int = 0
    signal_to_trade_pct: float | None = None


class RiskMetrics(BaseModel):
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    buy_hold_return_pct: float | None = None
    alpha_vs_buy_hold_pct: float | None = None
    exposure_time_pct: float | None = None
    avg_drawdown_pct: float | None = None
    max_drawdown_duration: str | None = None


class RunSummary(BaseModel):
    start_value: float
    end_value: float
    return_pct: float
    max_drawdown_pct: float | None = None
    sharpe_ratio: float | None = None
    total_trades: int = 0
    won_trades: int = 0
    lost_trades: int = 0
    trade_diagnostics: TradeDiagnostics | None = None
    filter_diagnostics: FilterDiagnostics | None = None
    risk_metrics: RiskMetrics | None = None


class RunResult(BaseModel):
    run_id: str
    name: str | None = None
    status: Literal["success", "failed"]
    strategy: str
    symbol: str | None = None
    data_source: str
    summary: RunSummary | None = None
    analyzers: dict[str, Any] = Field(default_factory=dict)
    orders: list[OrderRecord] = Field(default_factory=list)
    trades: list[TradeRecord] = Field(default_factory=list)
    rejections: list[RejectionRecord] = Field(default_factory=list)
    equity_curve: list[EquityPoint] = Field(default_factory=list)
    error: RunError | None = None


class StrategyAggregate(BaseModel):
    strategy: str
    symbols: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    successful_runs: int = 0
    failed_runs: int = 0
    summary: RunSummary
    equity_curve: list[EquityPoint] = Field(default_factory=list)


class PortfolioAggregate(BaseModel):
    total_net_pnl: float
    total_trades: int
    won_trades: int
    lost_trades: int
    win_rate_pct: float | None = None
    combined_return_pct: float | None = None
    best_run_id: str | None = None
    worst_run_id: str | None = None


class ReportAggregates(BaseModel):
    portfolio: PortfolioAggregate | None = None
    by_strategy: list[StrategyAggregate] = Field(default_factory=list)


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
    aggregates: ReportAggregates | None = None
