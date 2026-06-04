from __future__ import annotations

import pandas as pd

from app.intraday.walk_forward import make_walk_forward_folds, resolve_walk_forward_config


def test_intraday_walk_forward_is_chronological_and_embargoed() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=120, freq="D", tz="UTC"),
            "feature_1": list(range(120)),
        }
    )
    config = resolve_walk_forward_config(
        df,
        {
            "timestamp_column": "timestamp",
            "train_days": 30,
            "validation_days": 5,
            "test_days": 5,
            "step_days": 5,
            "embargo_bars": 2,
            "min_train_rows": 20,
            "min_validation_rows": 3,
            "min_test_rows": 3,
        },
    )
    folds = make_walk_forward_folds(df, config)
    assert folds
    for fold in folds:
        assert fold.train_start < fold.validation_start < fold.validation_end < fold.test_start < fold.test_end
        assert fold.test_start - fold.validation_end == pd.Timedelta(days=2)
