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


class CandidateRecord(BaseModel):
    candidate_id: str
    strategy_id: str
    symbol: str
    timestamp: str
    side: Literal["LONG", "SHORT"] = "LONG"
    entry_price: float
    entry_type: Literal["CLOSE", "NEXT_OPEN", "MARKET", "LIMIT", "MID"] = "CLOSE"
    planned_stop_pct: float
    planned_target_pct: float | None = None
    planned_horizon_bars: int
    signal_score: float | None = None
    signal_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    was_traded: bool = False
    reject_reason: str | None = None


class CandidateDiagnostics(BaseModel):
    total_candidates: int = 0
    traded_candidates: int = 0
    rejected_candidates: int = 0


LabelQualityFlag = Literal["OK", "MISSING_BARS", "BAD_PRICE", "AMBIGUOUS_INTRABAR"]
OutcomeExitReason = Literal["STOP", "TARGET", "TIME", "DATA_ERROR"]
FeatureQualityFlag = Literal["OK", "INSUFFICIENT_HISTORY"]


class OutcomeLabelRecord(BaseModel):
    candidate_id: str
    label_version: str
    entry_price: float
    horizon_bars: int
    stop_pct: float
    target_pct: float | None = None
    mae_pct: float
    mae_abs_pct: float
    mae_atr: float | None = None
    mfe_pct: float
    final_return_pct: float
    realized_R: float
    hit_stop: bool
    hit_target: bool
    hit_stop_before_target: bool
    bars_to_stop: int | None = None
    bars_to_target: int | None = None
    bars_held: int
    exit_reason: OutcomeExitReason
    label_quality_flag: LabelQualityFlag


class FeatureSnapshotRecord(BaseModel):
    candidate_id: str
    feature_version: str
    feature_timestamp: str
    feature_quality_flag: FeatureQualityFlag = "OK"
    return_5: float | None = None
    return_10: float | None = None
    return_20: float | None = None
    trend_slope_20: float | None = None
    trend_slope_50: float | None = None
    sma_20_distance: float | None = None
    sma_50_distance: float | None = None
    rsi_14: float | None = None
    return_zscore_20: float | None = None
    gap_pct: float | None = None
    consecutive_up_bars: int | None = None
    volume_zscore_20: float | None = None
    relative_volume_20: float | None = None
    atr_14_pct: float | None = None
    realized_vol_10: float | None = None
    realized_vol_20: float | None = None
    vol_percentile_60: float | None = None
    atr_expansion_10_50: float | None = None
    dollar_volume_20: float | None = None
    volume_percentile_60: float | None = None
    index_return_20: float | None = None
    index_trend_slope_50: float | None = None
    correlation_to_index_60: float | None = None
    beta_to_index_60: float | None = None
    metadata_features: dict[str, Any] = Field(default_factory=dict)


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
    candidates: list[CandidateRecord] = Field(default_factory=list)
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
