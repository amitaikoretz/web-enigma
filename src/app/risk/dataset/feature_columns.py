from __future__ import annotations

from typing import Iterable

import pandas as pd
from pandas.api.types import is_bool_dtype, is_numeric_dtype

from app.output.models import FeatureSnapshotRecord

_FEATURE_SNAPSHOT_COLUMNS = {
    name
    for name in FeatureSnapshotRecord.model_fields
    if name not in {"candidate_id", "feature_version", "feature_timestamp", "feature_quality_flag", "metadata_features"}
}

_CANDIDATE_FEATURE_COLUMNS = {
    "entry_price",
    "planned_stop_pct",
    "planned_target_pct",
    "planned_horizon_bars",
    "signal_score",
}

_EXCLUDED_FEATURE_COLUMNS = {
    "dataset_version",
    "label_version",
    "feature_version",
    "candidate_id",
    "strategy_id",
    "symbol",
    "timestamp",
    "side",
    "entry_type",
    "signal_reason",
    "was_traded",
    "reject_reason",
    "run_id",
    "resolution",
    "feed",
    "data_source",
    "fill_model",
    "start_date",
    "end_date",
    "benchmark_symbol",
    "source_report_path",
    "csv_path",
    "horizon_bars",
    "stop_pct",
    "target_pct",
    "mae_pct",
    "mae_abs_pct",
    "mae_atr",
    "mfe_pct",
    "final_return_pct",
    "realized_R",
    "hit_stop",
    "hit_target",
    "hit_stop_before_target",
    "bars_to_stop",
    "bars_to_target",
    "bars_held",
    "exit_reason",
    "label_quality_flag",
    "feature_timestamp",
    "feature_quality_flag",
}


def _is_numeric_like(series: pd.Series) -> bool:
    if is_bool_dtype(series) or is_numeric_dtype(series):
        return True
    # Allow all-null metadata columns to pass through so feature schemas stay stable even when
    # a particular dataset does not populate a given optional feature.
    return bool(series.dropna().empty)


def select_risk_feature_columns(
    frame: pd.DataFrame,
    requested_columns: Iterable[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return the numeric risk-model feature columns from a dataset frame.

    The dataset builder stores candidate metadata, labels, and feature snapshots together in one
    parquet table. This helper keeps only the actual model inputs, preserving their on-disk order
    while filtering out string metadata and label leakage columns.
    """

    if requested_columns is None:
        columns = [
            col
            for col in frame.columns
            if col in _FEATURE_SNAPSHOT_COLUMNS or col in _CANDIDATE_FEATURE_COLUMNS or col.startswith("meta_")
        ]
    else:
        columns = [col for col in requested_columns if col in frame.columns]

    selected: list[str] = []
    skipped: list[str] = []
    for col in columns:
        if col in _EXCLUDED_FEATURE_COLUMNS:
            skipped.append(col)
            continue
        if col in _FEATURE_SNAPSHOT_COLUMNS or col in _CANDIDATE_FEATURE_COLUMNS:
            selected.append(col)
            continue
        if col.startswith("meta_") and _is_numeric_like(frame[col]):
            selected.append(col)
            continue
        if requested_columns is not None and _is_numeric_like(frame[col]):
            selected.append(col)
            continue
        skipped.append(col)

    return selected, skipped
