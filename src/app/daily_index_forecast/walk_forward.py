from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class DailyIndexWalkForwardFold:
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
class DailyIndexWalkForwardSplit:
    holdout_start: pd.Timestamp
    holdout_end: pd.Timestamp


def _session_dates(frame: pd.DataFrame, column: str = "session_date") -> pd.Series:
    ts = pd.to_datetime(frame[column], errors="coerce")
    if ts.isna().any():
        bad = int(ts.isna().sum())
        raise ValueError(f"Column '{column}' contains {bad} invalid session dates")
    return ts.dt.tz_localize(None)


def _midnight_utc(ts: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(ts).tz_localize("UTC") if ts.tzinfo is None else pd.Timestamp(ts).tz_convert("UTC")


def _scale_window_sizes(
    *,
    train_days: int,
    validation_days: int,
    test_days: int,
    available_days: int,
) -> tuple[int, int, int]:
    requested = [train_days, validation_days, test_days]
    requested_total = sum(requested)
    if available_days >= requested_total:
        return train_days, validation_days, test_days

    scale = available_days / requested_total
    effective = [max(1, int(day_count * scale)) for day_count in requested]

    # Trim the largest windows first if rounding pushed us over the available history.
    while sum(effective) > available_days:
        largest_index = max(range(len(effective)), key=lambda idx: effective[idx])
        if effective[largest_index] > 1:
            effective[largest_index] -= 1
            continue
        decrementable = next((idx for idx, value in enumerate(effective) if value > 1), None)
        if decrementable is None:
            break
        effective[decrementable] -= 1

    return effective[0], effective[1], effective[2]


def resolve_holdout_start(frame: pd.DataFrame, *, holdout_days: int) -> pd.Timestamp:
    dates = _session_dates(frame)
    unique_dates = pd.Index(dates.unique()).sort_values()
    if len(unique_dates) <= holdout_days:
        raise ValueError("Not enough sessions to reserve a holdout window")
    return _midnight_utc(pd.Timestamp(unique_dates[-holdout_days]))


def make_walk_forward_folds(
    frame: pd.DataFrame,
    *,
    train_days: int,
    validation_days: int,
    test_days: int,
    step_days: int,
    embargo_days: int,
    min_train_rows: int,
    min_validation_rows: int,
    min_test_rows: int,
    min_holdout_rows: int,
    holdout_days: int,
) -> tuple[list[DailyIndexWalkForwardFold], DailyIndexWalkForwardSplit]:
    if train_days <= 0 or validation_days <= 0 or test_days <= 0 or step_days <= 0:
        raise ValueError("walk-forward window sizes must be positive")
    if embargo_days < 0:
        raise ValueError("embargo_days must be non-negative")

    dates = _session_dates(frame)
    ordered = frame.assign(__session_date=dates).sort_values(["__session_date"], kind="mergesort")
    ordered_dates = ordered["__session_date"]
    unique_dates = pd.Index(ordered_dates.unique()).sort_values()
    if len(unique_dates) < 4:
        raise ValueError("Not enough sessions for walk-forward folds")

    effective_holdout_days = min(holdout_days, max(1, len(unique_dates) - 3))
    holdout_start = resolve_holdout_start(ordered, holdout_days=effective_holdout_days)
    holdout_mask = pd.to_datetime(ordered_dates).dt.tz_localize("UTC") >= holdout_start
    holdout = ordered.loc[holdout_mask]
    if len(holdout) < min_holdout_rows:
        raise ValueError("Holdout window does not contain enough rows")

    historical = ordered.loc[~holdout_mask]
    historical_dates = pd.Index(historical["__session_date"].unique()).sort_values()
    effective_train_days, effective_validation_days, effective_test_days = _scale_window_sizes(
        train_days=train_days,
        validation_days=validation_days,
        test_days=test_days,
        available_days=len(historical_dates),
    )
    if len(historical_dates) < effective_train_days + effective_validation_days + effective_test_days:
        raise ValueError("Not enough sessions for walk-forward folds")

    folds: list[DailyIndexWalkForwardFold] = []
    fold_id = 0
    anchor_index = 0
    while (
        anchor_index
        + effective_train_days
        + effective_validation_days
        + embargo_days
        + effective_test_days
        <= len(historical_dates)
    ):
        train_start = _midnight_utc(pd.Timestamp(historical_dates[anchor_index]))
        train_end = _midnight_utc(
            pd.Timestamp(historical_dates[anchor_index + effective_train_days - 1]) + pd.Timedelta(days=1)
        )
        validation_start = train_end
        validation_end = _midnight_utc(
            pd.Timestamp(historical_dates[anchor_index + effective_train_days + effective_validation_days - 1])
            + pd.Timedelta(days=1)
        )
        test_start_index = anchor_index + effective_train_days + effective_validation_days + embargo_days
        test_start = _midnight_utc(pd.Timestamp(historical_dates[test_start_index]))
        test_end = _midnight_utc(
            pd.Timestamp(
                historical_dates[
                    anchor_index
                    + effective_train_days
                    + effective_validation_days
                    + embargo_days
                    + effective_test_days
                    - 1
                ]
            )
            + pd.Timedelta(days=1)
        )

        train_mask = (pd.to_datetime(ordered_dates).dt.tz_localize("UTC") >= train_start) & (
            pd.to_datetime(ordered_dates).dt.tz_localize("UTC") < validation_start
        )
        validation_mask = (pd.to_datetime(ordered_dates).dt.tz_localize("UTC") >= validation_start) & (
            pd.to_datetime(ordered_dates).dt.tz_localize("UTC") < validation_end
        )
        test_mask = (pd.to_datetime(ordered_dates).dt.tz_localize("UTC") >= test_start) & (
            pd.to_datetime(ordered_dates).dt.tz_localize("UTC") < test_end
        )

        n_train = int(train_mask.sum())
        n_validation = int(validation_mask.sum())
        n_test = int(test_mask.sum())
        if n_train < min_train_rows or n_validation < min_validation_rows or n_test < min_test_rows:
            anchor_index += step_days
            continue

        folds.append(
            DailyIndexWalkForwardFold(
                fold_id=fold_id,
                train_start=train_start,
                train_end=validation_start,
                validation_start=validation_start,
                validation_end=validation_end,
                test_start=test_start,
                test_end=test_end,
                n_train=n_train,
                n_validation=n_validation,
                n_test=n_test,
            )
        )
        fold_id += 1
        anchor_index += step_days

    if not folds:
        raise ValueError("No walk-forward folds could be created from the provided dataset")

    return folds, DailyIndexWalkForwardSplit(
        holdout_start=holdout_start,
        holdout_end=_midnight_utc(pd.Timestamp(unique_dates.max()) + pd.Timedelta(days=1)),
    )
