from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass(frozen=True)
class IntradayWalkForwardFold:
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


@dataclass(frozen=True)
class IntradayWalkForwardConfig:
    timestamp_column: str = "timestamp"
    train_days: int = 60
    validation_days: int = 5
    test_days: int = 5
    step_days: int = 5
    embargo_bars: int = 1
    min_train_rows: int = 200
    min_validation_rows: int = 50
    min_test_rows: int = 50


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


def resolve_walk_forward_config(frame: pd.DataFrame, train_cfg: dict[str, Any] | None = None) -> IntradayWalkForwardConfig:
    cfg = train_cfg or {}
    timestamp_column = str(cfg.get("timestamp_column", "timestamp"))
    ts = _parse_timestamp_series(frame, timestamp_column)
    row_count = max(1, len(frame))

    train_days = int(cfg.get("train_days", 60))
    validation_days = int(cfg.get("validation_days", 5))
    test_days = int(cfg.get("test_days", 5))
    step_days = int(cfg.get("step_days", max(5, test_days)))
    embargo_bars = int(cfg.get("embargo_bars", 1))

    min_train_rows = int(cfg.get("min_train_rows", max(200, row_count // 10)))
    min_validation_rows = int(cfg.get("min_validation_rows", max(50, row_count // 20)))
    min_test_rows = int(cfg.get("min_test_rows", max(50, row_count // 20)))

    if train_days <= 0 or validation_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("walk-forward window sizes must be positive")
    if embargo_bars < 0:
        raise ValueError("embargo_bars must be non-negative")
    if ts.empty:
        raise ValueError("walk-forward requires at least one timestamp")

    return IntradayWalkForwardConfig(
        timestamp_column=timestamp_column,
        train_days=train_days,
        validation_days=validation_days,
        test_days=test_days,
        step_days=step_days,
        embargo_bars=embargo_bars,
        min_train_rows=min_train_rows,
        min_validation_rows=min_validation_rows,
        min_test_rows=min_test_rows,
    )


def make_walk_forward_folds(frame: pd.DataFrame, config: IntradayWalkForwardConfig) -> list[IntradayWalkForwardFold]:
    ts = _parse_timestamp_series(frame, config.timestamp_column)
    ordered = frame.assign(__wf_timestamp=ts).sort_values(["__wf_timestamp"], kind="mergesort")
    ordered_ts = ordered["__wf_timestamp"]
    min_ts = ordered_ts.min()
    max_ts = ordered_ts.max()
    bar_delta = _median_bar_delta(ordered_ts)
    embargo_delta = bar_delta * config.embargo_bars

    train_td = pd.Timedelta(days=config.train_days)
    validation_td = pd.Timedelta(days=config.validation_days)
    test_td = pd.Timedelta(days=config.test_days)
    step_td = pd.Timedelta(days=config.step_days)

    folds: list[IntradayWalkForwardFold] = []
    fold_id = 0
    anchor = min_ts
    while True:
        train_start = pd.Timestamp(anchor)
        train_end = train_start + train_td
        validation_start = train_end
        validation_end = validation_start + validation_td
        test_start = validation_end + embargo_delta
        test_end = test_start + test_td

        if test_start > max_ts:
            break

        train_mask = (ordered_ts >= train_start) & (ordered_ts < train_end)
        validation_mask = (ordered_ts >= validation_start) & (ordered_ts < validation_end)
        test_mask = (ordered_ts >= test_start) & (ordered_ts < test_end)

        train_rows = ordered.loc[train_mask]
        validation_rows = ordered.loc[validation_mask]
        test_rows = ordered.loc[test_mask]

        if (
            len(train_rows) < config.min_train_rows
            or len(validation_rows) < config.min_validation_rows
            or len(test_rows) < config.min_test_rows
        ):
            anchor = anchor + step_td
            continue

        folds.append(
            IntradayWalkForwardFold(
                fold_id=fold_id,
                train_start=train_start,
                train_end=train_end,
                validation_start=validation_start,
                validation_end=validation_end,
                test_start=test_start,
                test_end=test_end,
                n_train=int(len(train_rows)),
                n_validation=int(len(validation_rows)),
                n_test=int(len(test_rows)),
            )
        )
        fold_id += 1
        anchor = anchor + step_td

    return folds

