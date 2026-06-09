from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    model_config = ConfigDict(extra="forbid")

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
    max_parquet_file_size_bytes: int = 10 * 1024 * 1024
    parquet_split_primary_keys: list[str] = Field(default_factory=lambda: ["symbol"])
    parquet_split_fallback_keys: list[str] = Field(default_factory=lambda: ["run_id", "candidate_id"])

    @model_validator(mode="after")
    def _validate_split_config(self) -> "RiskDatasetConfig":
        if self.max_parquet_file_size_bytes <= 0:
            raise ValueError("max_parquet_file_size_bytes must be positive")
        if not self.parquet_split_primary_keys:
            raise ValueError("parquet_split_primary_keys must not be empty")
        if len(set(self.parquet_split_primary_keys)) != len(self.parquet_split_primary_keys):
            raise ValueError("parquet_split_primary_keys must be unique")
        if len(set(self.parquet_split_fallback_keys)) != len(self.parquet_split_fallback_keys):
            raise ValueError("parquet_split_fallback_keys must be unique")
        if set(self.parquet_split_primary_keys) & set(self.parquet_split_fallback_keys):
            raise ValueError("parquet_split_primary_keys and parquet_split_fallback_keys must not overlap")
        return self


class RiskDatasetChunkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    row_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    chunk_index: int = Field(ge=0)
    split_key_values: dict[str, str | None] = Field(default_factory=dict)


class RiskDatasetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    max_parquet_file_size_bytes: int = 10 * 1024 * 1024
    primary_split_keys: list[str] = Field(default_factory=lambda: ["symbol"])
    fallback_split_keys: list[str] = Field(default_factory=lambda: ["run_id", "candidate_id"])
    chunk_count: int = 1
    total_parquet_bytes: int = 0
    files: list[RiskDatasetChunkRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_manifest(self) -> "RiskDatasetManifest":
        if not self.primary_split_keys:
            raise ValueError("primary_split_keys must not be empty")
        if len(set(self.primary_split_keys)) != len(self.primary_split_keys):
            raise ValueError("primary_split_keys must be unique")
        if len(set(self.fallback_split_keys)) != len(self.fallback_split_keys):
            raise ValueError("fallback_split_keys must be unique")
        if set(self.primary_split_keys) & set(self.fallback_split_keys):
            raise ValueError("primary_split_keys and fallback_split_keys must not overlap")
        if self.chunk_count != len(self.files):
            raise ValueError("chunk_count must match the number of files")
        if self.total_parquet_bytes != sum(file.size_bytes for file in self.files):
            raise ValueError("total_parquet_bytes must equal the sum of file sizes")
        return self


class RunRiskAuxiliaryRows(BaseModel):
    labels: list[OutcomeLabelRecord] = Field(default_factory=list)
    features: list[FeatureSnapshotRecord] = Field(default_factory=list)
