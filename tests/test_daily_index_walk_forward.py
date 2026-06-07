from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pandas as pd

from app.daily_index_forecast.walk_forward import make_walk_forward_folds


def test_daily_index_walk_forward_uses_holdout_minimum_rows() -> None:
    base = datetime(2024, 1, 1, tzinfo=UTC)
    rows = []
    for day in range(10):
        for row in range(2):
            ts = base + timedelta(days=day, hours=row)
            rows.append(
                {
                    "session_date": ts.date(),
                    "decision_timestamp": ts,
                }
            )
    frame = pd.DataFrame(rows)

    folds, split = make_walk_forward_folds(
        frame,
        train_days=3,
        validation_days=2,
        test_days=1,
        step_days=1,
        embargo_days=0,
        min_train_rows=1,
        min_validation_rows=1,
        min_test_rows=1,
        min_holdout_rows=4,
        holdout_days=2,
    )

    assert folds
    assert split.holdout_start == pd.Timestamp("2024-01-09", tz="UTC")
