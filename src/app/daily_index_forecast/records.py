from __future__ import annotations

from datetime import date, datetime
from typing import Any, TypeVar

import pandas as pd
from pydantic import BaseModel, Field


class DailyIndexFeatureRecord(BaseModel):
    symbol: str
    session_date: date
    decision_time: str
    decision_timestamp: datetime
    session_open_timestamp: datetime
    session_close_timestamp: datetime
    bars_seen: int
    opening_window_minutes: int
    open_price: float
    high_price: float
    low_price: float
    last_price: float
    volume_so_far: float
    dollar_volume_so_far: float
    opening_window_return_pct: float | None = None
    opening_window_range_pct: float | None = None
    opening_window_close_location_pct: float | None = None
    gap_return_pct: float | None = None
    prior_session_return_pct: float | None = None
    prior_session_range_pct: float | None = None
    prior_session_volume: float | None = None
    prior_session_realized_volatility: float | None = None
    rolling_return_5: float | None = None
    rolling_return_20: float | None = None
    rolling_volatility_5: float | None = None
    rolling_volatility_20: float | None = None
    rolling_volume_z_20: float | None = None
    benchmark_return_5: float | None = None
    benchmark_return_20: float | None = None
    benchmark_volatility_20: float | None = None
    relative_return_20: float | None = None
    correlation_to_benchmark_20: float | None = None
    beta_to_benchmark_20: float | None = None
    day_of_week: int
    month: int
    is_month_start: bool
    is_month_end: bool
    minutes_since_open: int
    minutes_to_close: int
    feature_quality_flag: str = Field(default="OK")


class DailyIndexLabelRecord(BaseModel):
    symbol: str
    session_date: date
    decision_time: str
    decision_timestamp: datetime
    exit_timestamp: datetime
    entry_price: float
    exit_price: float
    return_to_close_pct: float
    return_to_close_bps: float
    net_return_after_cost_bps: float
    positive_after_cost: bool
    intraday_max_runup_bps: float | None = None
    intraday_max_drawdown_bps: float | None = None
    post_decision_realized_volatility_bps: float | None = None
    label_quality_flag: str = Field(default="OK")


class DailyIndexFeatureRow(BaseModel):
    symbol: str
    session_date: date
    decision_time: str
    decision_timestamp: datetime
    feature_quality_flag: str
    features: dict[str, float | None] = Field(default_factory=dict)


class DailyIndexLabelRow(BaseModel):
    symbol: str
    session_date: date
    decision_time: str
    decision_timestamp: datetime
    label_quality_flag: str
    labels: dict[str, float | bool | None] = Field(default_factory=dict)


class DailyIndexDatasetManifest(BaseModel):
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


class DailyIndexFoldMetric(BaseModel):
    fold_id: int
    train_start: str
    train_end: str
    validation_start: str
    validation_end: str
    test_start: str
    test_end: str
    n_train: int
    n_validation: int
    n_test: int
    validation: dict[str, Any] = Field(default_factory=dict)
    test: dict[str, Any] = Field(default_factory=dict)


class DailyIndexMetrics(BaseModel):
    generated_at: datetime
    group_id: str
    feature_run_id: str
    n_rows: int
    selected_alpha: float
    selected_fold_id: int | None = None
    feature_columns: list[str] = Field(default_factory=list)
    walk_forward: dict[str, Any] = Field(default_factory=dict)
    holdout: dict[str, Any] = Field(default_factory=dict)
    aggregate: dict[str, Any] = Field(default_factory=dict)
    fold_metrics: list[DailyIndexFoldMetric] = Field(default_factory=list)


class DailyIndexModelArtifact(BaseModel):
    model_version: str
    feature_version: str
    label_version: str
    dataset_version: str
    feature_run_id: str
    selected_fold_id: int | None = None
    selected_alpha: float
    selected_features: list[str] = Field(default_factory=list)
    scaler_mean: list[float] = Field(default_factory=list)
    scaler_scale: list[float] = Field(default_factory=list)
    coefficients: list[float] = Field(default_factory=list)
    intercept: float
    residual_std: float
    costs: dict[str, float] = Field(default_factory=dict)
    walk_forward: dict[str, Any] = Field(default_factory=dict)
    holdout_metrics: dict[str, Any] = Field(default_factory=dict)
    aggregate_metrics: dict[str, Any] = Field(default_factory=dict)


RecordT = TypeVar("RecordT", bound=BaseModel)


def records_to_frame(records: list[RecordT]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame()
    return pd.DataFrame([record.model_dump(mode="json") for record in records])


def frame_to_records(frame: pd.DataFrame, model: type[RecordT]) -> list[RecordT]:
    if frame.empty:
        return []
    return [model.model_validate(row.to_dict()) for _, row in frame.iterrows()]

