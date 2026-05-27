from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

LabelQualityFlag = Literal["OK", "MISSING_BARS", "BAD_PRICE", "AMBIGUOUS_INTRABAR"]
ExitReason = Literal["STOP", "TARGET", "TIME", "DATA_ERROR"]
FeatureQualityFlag = Literal["OK", "INSUFFICIENT_HISTORY"]
AmbiguousIntrabarPolicy = Literal["assume_stop_first", "assume_target_first"]


class EnrichedCandidate(BaseModel):
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
    run_id: str
    resolution: str | None = None
    feed: str | None = None
    data_source: str
    fill_model: str = "close"
    start_date: date | None = None
    end_date: date | None = None
    benchmark_symbol: str | None = None
    source_report_path: str
    csv_path: str | None = None


class OutcomeLabel(BaseModel):
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
    exit_reason: ExitReason
    label_quality_flag: LabelQualityFlag


class FeatureSnapshot(BaseModel):
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


class RiskDatasetConfig(BaseModel):
    dataset_version: str = "risk_dataset_v1"
    label_version: str = "labels_v1"
    feature_version: str = "features_v1"
    ambiguous_intrabar_policy: AmbiguousIntrabarPolicy = "assume_stop_first"
    min_history_bars: int = 60
    lookback_bars: int = 60
    winsorize_quantiles: list[float] = Field(default_factory=lambda: [0.01, 0.99])
    vol_percentile_window: int = 60
    include_index_features: bool = True
    default_benchmark_symbol: str = "SPY"
    cache_directory: str = ".cache/backtest-data"
    cache_enabled: bool = True


class RiskDatasetManifest(BaseModel):
    generated_at: datetime
    dataset_version: str
    label_version: str
    feature_version: str
    config_hash: str
    source_report_paths: list[str]
    total_candidates: int
    labeled_rows: int
    feature_rows: int
    joined_rows: int
    dropped_label_rows: int
    dropped_feature_rows: int
    duplicate_candidate_ids: int
    output_path: str
