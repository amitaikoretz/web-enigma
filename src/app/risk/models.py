from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.output.models import (
    FeatureQualityFlag,
    FeatureSnapshotRecord,
    LabelQualityFlag,
    OutcomeExitReason,
    OutcomeLabelRecord,
)

AmbiguousIntrabarPolicy = Literal["assume_stop_first", "assume_target_first"]

OutcomeLabel = OutcomeLabelRecord
FeatureSnapshot = FeatureSnapshotRecord
ExitReason = OutcomeExitReason


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


class RunRiskAuxiliaryRows(BaseModel):
    labels: list[OutcomeLabelRecord] = Field(default_factory=list)
    features: list[FeatureSnapshotRecord] = Field(default_factory=list)
