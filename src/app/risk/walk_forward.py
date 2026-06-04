from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

_TIMESTAMP_COLUMNS = ("timestamp", "feature_timestamp")


@dataclass(frozen=True)
class WalkForwardConfig:
    timestamp_column: str
    train_days: int
    test_days: int
    step_days: int
    calibration_fraction: float
    embargo_bars: int
    min_train_rows: int
    min_validation_rows: int
    min_test_rows: int


@dataclass(frozen=True)
class WalkForwardFold:
    fold_id: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    n_train: int
    n_validation: int
    n_test: int


def infer_walk_forward_timestamp_column(frame: pd.DataFrame) -> str:
    for column in _TIMESTAMP_COLUMNS:
        if column in frame.columns:
            return column
    raise ValueError(
        "Risk model dataset is missing a timestamp column; expected 'timestamp' or 'feature_timestamp'"
    )


def _parse_timestamp_series(frame: pd.DataFrame, column: str) -> pd.Series:
    ts = pd.to_datetime(frame[column], utc=True, errors="coerce")
    if ts.isna().any():
        bad_count = int(ts.isna().sum())
        raise ValueError(f"Timestamp column '{column}' contains {bad_count} unparseable values")
    return ts


def _median_bar_delta(ts: pd.Series) -> pd.Timedelta:
    unique_ts = pd.Series(pd.Index(ts).unique()).sort_values(ignore_index=True)
    if len(unique_ts) < 2:
        return pd.Timedelta(0)
    diffs = unique_ts.diff().dropna()
    if diffs.empty:
        return pd.Timedelta(0)
    return pd.Timedelta(diffs.median())


def resolve_walk_forward_config(
    frame: pd.DataFrame,
    train_cfg: dict[str, Any] | None = None,
    *,
    timestamp_column: str | None = None,
) -> WalkForwardConfig:
    cfg = train_cfg or {}
    ts_col = timestamp_column or infer_walk_forward_timestamp_column(frame)
    ts = _parse_timestamp_series(frame, ts_col)
    min_ts = ts.min()
    max_ts = ts.max()
    span_days = max(1, int((max_ts - min_ts).total_seconds() // 86400) or 1)
    row_count = max(1, len(frame))

    calibration_fraction = float(cfg.get("walk_forward_calibration_fraction", cfg.get("calibration_test_size", 0.2)))
    if not 0.0 < calibration_fraction < 1.0:
        raise ValueError("walk-forward calibration fraction must be between 0 and 1")

    train_days = int(cfg.get("walk_forward_train_days", max(14, int(span_days * 0.6))))
    test_days = int(cfg.get("walk_forward_test_days", max(7, int(span_days * 0.2))))
    step_days = int(cfg.get("walk_forward_step_days", max(7, test_days)))
    embargo_bars = int(cfg.get("walk_forward_embargo_bars", cfg.get("embargo_bars", 10)))

    min_train_rows = int(cfg.get("walk_forward_min_train_rows", max(20, row_count // 10)))
    min_validation_rows = int(cfg.get("walk_forward_min_validation_rows", max(10, row_count // 20)))
    min_test_rows = int(cfg.get("walk_forward_min_test_rows", max(10, row_count // 20)))

    if train_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("walk-forward window sizes must be positive")
    if embargo_bars < 0:
        raise ValueError("walk-forward embargo_bars must be non-negative")

    return WalkForwardConfig(
        timestamp_column=ts_col,
        train_days=train_days,
        test_days=test_days,
        step_days=step_days,
        calibration_fraction=calibration_fraction,
        embargo_bars=embargo_bars,
        min_train_rows=min_train_rows,
        min_validation_rows=min_validation_rows,
        min_test_rows=min_test_rows,
    )


def make_walk_forward_folds(
    frame: pd.DataFrame,
    config: WalkForwardConfig,
) -> list[WalkForwardFold]:
    ts = _parse_timestamp_series(frame, config.timestamp_column)
    ordered = frame.assign(__wf_timestamp=ts).sort_values(["__wf_timestamp"], kind="mergesort")
    ordered_ts = ordered["__wf_timestamp"]
    min_ts = ordered_ts.min()
    max_ts = ordered_ts.max()
    bar_delta = _median_bar_delta(ordered_ts)
    embargo_delta = bar_delta * config.embargo_bars

    train_td = pd.Timedelta(days=config.train_days)
    test_td = pd.Timedelta(days=config.test_days)
    step_td = pd.Timedelta(days=config.step_days)

    folds: list[WalkForwardFold] = []
    fold_id = 0
    anchor = min_ts

    while True:
        train_start = pd.Timestamp(anchor)
        train_end = train_start + train_td
        test_start = train_end + embargo_delta
        test_end = test_start + test_td

        if test_start > max_ts:
            break

        train_mask = (ordered_ts >= train_start) & (ordered_ts < train_end)
        test_mask = (ordered_ts >= test_start) & (ordered_ts < test_end)

        train_rows = ordered.loc[train_mask]
        test_rows = ordered.loc[test_mask]
        if len(train_rows) < config.min_train_rows or len(test_rows) < config.min_test_rows:
            anchor = anchor + step_td
            continue

        split_ts = pd.Timestamp(train_rows["__wf_timestamp"].quantile(1.0 - config.calibration_fraction))
        if split_ts <= train_start or split_ts >= train_end:
            anchor = anchor + step_td
            continue

        validation_mask = train_mask & (ordered_ts >= split_ts)
        train_inner_mask = train_mask & (ordered_ts < split_ts)
        validation_rows = ordered.loc[validation_mask]
        train_inner_rows = ordered.loc[train_inner_mask]

        if (
            len(train_inner_rows) < config.min_train_rows
            or len(validation_rows) < config.min_validation_rows
            or len(test_rows) < config.min_test_rows
        ):
            anchor = anchor + step_td
            continue

        folds.append(
            WalkForwardFold(
                fold_id=fold_id,
                train_start=train_start,
                train_end=train_end,
                validation_start=split_ts,
                validation_end=train_end,
                test_start=test_start,
                test_end=test_end,
                n_train=int(len(train_inner_rows)),
                n_validation=int(len(validation_rows)),
                n_test=int(len(test_rows)),
            )
        )
        fold_id += 1
        anchor = anchor + step_td

    return folds
