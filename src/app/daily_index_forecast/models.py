from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.api.schemas.market_data import MarketDataResponse

from app.config.models import AlpacaDataSource, CsvDataSource, DataCacheConfig, YahooDataSource

DataSource = CsvDataSource | YahooDataSource | AlpacaDataSource
DailyIndexForecastStatus = Literal["pending", "running", "succeeded", "failed", "canceled"]
DailyIndexTaskType = Literal["regression"]


class DailyIndexSeriesSpec(BaseModel):
    symbol: str | None = None
    data: DataSource

    @model_validator(mode="after")
    def ensure_symbol(self) -> "DailyIndexSeriesSpec":
        if self.symbol is None and hasattr(self.data, "symbol"):
            object.__setattr__(self, "symbol", getattr(self.data, "symbol"))
        if not self.symbol or not self.symbol.strip():
            raise ValueError("symbol is required")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        return self


class DailyIndexUniverseConfig(BaseModel):
    start_date: date
    end_date: date
    decision_times: list[str] = Field(default_factory=lambda: ["09:45"])
    symbols: list[DailyIndexSeriesSpec]
    benchmark: DailyIndexSeriesSpec | None = None

    @model_validator(mode="after")
    def validate_universe(self) -> "DailyIndexUniverseConfig":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        if not self.symbols:
            raise ValueError("At least one symbol is required")
        if not self.decision_times:
            raise ValueError("At least one decision time is required")
        normalized_times: list[str] = []
        for value in self.decision_times:
            text = value.strip()
            if not text:
                continue
            parts = text.split(":")
            if len(parts) < 2 or len(parts) > 3:
                raise ValueError(f"Invalid decision_time '{value}'")
            hours = int(parts[0])
            minutes = int(parts[1])
            seconds = int(parts[2]) if len(parts) == 3 else 0
            if hours < 0 or hours > 23 or minutes < 0 or minutes > 59 or seconds < 0 or seconds > 59:
                raise ValueError(f"Invalid decision_time '{value}'")
            normalized_times.append(f"{hours:02d}:{minutes:02d}:{seconds:02d}" if seconds else f"{hours:02d}:{minutes:02d}")
        object.__setattr__(self, "decision_times", normalized_times)
        return self


class DailyIndexFeatureConfig(BaseModel):
    opening_window_minutes: int = Field(default=15, gt=0)
    rolling_sessions: list[int] = Field(default_factory=lambda: [5, 20])
    benchmark_sessions: list[int] = Field(default_factory=lambda: [5, 20])
    use_calendar_features: bool = True
    use_cross_market_features: bool = True


class DailyIndexWalkForwardConfig(BaseModel):
    train_days: int = Field(default=90, gt=0)
    validation_days: int = Field(default=10, gt=0)
    test_days: int = Field(default=10, gt=0)
    step_days: int = Field(default=10, gt=0)
    embargo_days: int = Field(default=1, ge=0)
    holdout_days: int = Field(default=20, gt=0)
    min_train_rows: int = Field(default=60, gt=0)
    min_validation_rows: int = Field(default=10, gt=0)
    min_test_rows: int = Field(default=10, gt=0)
    min_holdout_rows: int = Field(default=10, gt=0)


class DailyIndexTrainConfig(BaseModel):
    alpha_grid: list[float] = Field(default_factory=lambda: [0.25, 1.0, 4.0, 16.0])
    residual_distribution: Literal["normal"] = "normal"
    random_seed: int = 7


class DailyIndexCostConfig(BaseModel):
    spread_bps: float = Field(default=1.5, ge=0)
    slippage_bps: float = Field(default=1.0, ge=0)
    impact_bps: float = Field(default=0.5, ge=0)

    @property
    def roundtrip_bps(self) -> float:
        return 2.0 * self.spread_bps + 2.0 * self.slippage_bps + self.impact_bps


class DailyIndexForecastCreateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    universe: DailyIndexUniverseConfig
    feature_config: DailyIndexFeatureConfig = Field(default_factory=DailyIndexFeatureConfig)
    walk_forward: DailyIndexWalkForwardConfig = Field(default_factory=DailyIndexWalkForwardConfig)
    train_config: DailyIndexTrainConfig = Field(default_factory=DailyIndexTrainConfig)
    costs: DailyIndexCostConfig = Field(default_factory=DailyIndexCostConfig)
    data_cache: DataCacheConfig = Field(default_factory=DataCacheConfig)


class DailyIndexForecastCreateResponse(BaseModel):
    group_id: str
    feature_run_id: str
    name: str | None = None
    status: DailyIndexForecastStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None


class DailyIndexForecastUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=128)


class DailyIndexForecastListItemResponse(BaseModel):
    group_id: str
    feature_run_id: str
    name: str | None = None
    created_at: datetime
    updated_at: datetime
    status: DailyIndexForecastStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    symbol: str
    benchmark_symbol: str | None = None
    decision_times: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    targets: list[str] = Field(default_factory=list)
    targets_total: int = 0
    targets_done: int = 0
    summary_metrics: dict[str, Any] | None = None
    artifact_dir: str
    feature_run_artifact_dir: str


class DailyIndexForecastTargetRowResponse(BaseModel):
    id: int
    group_id: str
    target_key: str
    task_type: DailyIndexTaskType | str
    status: DailyIndexForecastStatus | str
    model_artifact_path: str | None = None
    metrics: dict[str, Any] | None = None
    dataset_manifest_path: str | None = None
    feature_columns: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class DailyIndexForecastDatasetManifestSummary(BaseModel):
    generated_at: datetime
    dataset_version: str
    feature_version: str
    label_version: str
    model_version: str
    config_hash: str
    symbol_count: int
    benchmark_symbol: str | None = None
    start_date: date
    end_date: date
    decision_times: list[str] = Field(default_factory=list)
    total_source_rows: int
    feature_rows: int
    label_rows: int
    joined_rows: int
    dropped_feature_rows: int
    dropped_label_rows: int
    output_path: str
    features_path: str
    labels_path: str
    feature_columns: list[str] = Field(default_factory=list)


# Backward-compatible alias used by older pipeline code and artifacts.
DailyIndexDatasetManifestSummary = DailyIndexForecastDatasetManifestSummary


class DailyIndexForecastFeatureRunResponse(BaseModel):
    feature_run_id: str
    status: DailyIndexForecastStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    symbol: str
    benchmark_symbol: str | None = None
    decision_times: list[str] = Field(default_factory=list)
    start_date: date
    end_date: date
    params: dict[str, Any] = Field(default_factory=dict)
    artifact_dir: str
    manifest: DailyIndexForecastDatasetManifestSummary | None = None
    summary_metrics: dict[str, Any] | None = None
    features_parquet_path: str | None = None
    labels_parquet_path: str | None = None
    created_at: datetime
    updated_at: datetime


class DailyIndexForecastDetailResponse(BaseModel):
    group_id: str
    feature_run_id: str
    name: str | None = None
    created_at: datetime
    updated_at: datetime
    status: DailyIndexForecastStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    artifact_dir: str
    summary_metrics: dict[str, Any] | None = None
    feature_run: DailyIndexForecastFeatureRunResponse | None = None
    dataset_manifest: DailyIndexForecastDatasetManifestSummary | None = None
    targets: list[DailyIndexForecastTargetRowResponse] = Field(default_factory=list)


class DailyIndexForecastStatusResponse(BaseModel):
    group_id: str
    feature_run_id: str
    name: str | None = None
    status: DailyIndexForecastStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    argo_phase: str | None = None
    progress_pct: float = Field(default=0.0, ge=0, le=100)


class DailyIndexForecastWorkflowErrorResponse(BaseModel):
    group_id: str
    feature_run_id: str
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    argo_phase: str | None = None
    available: bool = False
    status_message: str | None = None
    failed_node_name: str | None = None
    failed_template_name: str | None = None
    error_exception: str | None = None
    error_code_location: str | None = None
    error_call_stack: list[str] = Field(default_factory=list)
    error_traceback: str | None = None


DailyIndexForecastSplitLabel = Literal["train", "validation", "test", "holdout", "other"]


class DailyIndexForecastChartPredictionRowResponse(BaseModel):
    session_date: date
    decision_time: str
    decision_timestamp: datetime
    predicted_bps: float
    actual_bps: float | None = None
    actual_after_cost: bool | None = None
    split_label: DailyIndexForecastSplitLabel


class DailyIndexForecastChartResponse(BaseModel):
    group_id: str
    symbol: str
    selected_date: date
    resolution: str
    cache_status: str
    source: Literal["stored", "computed"]
    bars: MarketDataResponse
    split_label: DailyIndexForecastSplitLabel
    predictions: list[DailyIndexForecastChartPredictionRowResponse] = Field(default_factory=list)
