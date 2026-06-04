from __future__ import annotations

import pandas as pd

from app.risk.walk_forward import make_walk_forward_folds, resolve_walk_forward_config


def test_walk_forward_folds_are_chronological_and_embargoed() -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=40, freq="D", tz="UTC"),
            "value": list(range(40)),
        }
    )
    config = resolve_walk_forward_config(
        df,
        {
            "walk_forward_train_days": 12,
            "walk_forward_test_days": 4,
            "walk_forward_step_days": 4,
            "walk_forward_calibration_fraction": 0.25,
            "walk_forward_embargo_bars": 2,
            "walk_forward_min_train_rows": 6,
            "walk_forward_min_validation_rows": 3,
            "walk_forward_min_test_rows": 2,
        },
    )

    folds = make_walk_forward_folds(df, config)

    assert folds
    for fold in folds:
        train = df[(df["timestamp"] >= fold.train_start) & (df["timestamp"] < fold.train_end)]
        train_inner = train[train["timestamp"] < fold.validation_start]
        validation = df[(df["timestamp"] >= fold.validation_start) & (df["timestamp"] < fold.validation_end)]
        test = df[(df["timestamp"] >= fold.test_start) & (df["timestamp"] < fold.test_end)]

        assert not train.empty
        assert not validation.empty
        assert not test.empty
        assert train_inner["timestamp"].max() < validation["timestamp"].min()
        assert validation["timestamp"].max() < test["timestamp"].min()
        assert fold.test_start - fold.train_end == pd.Timedelta(days=2)
        assert fold.n_train == len(train_inner)
        assert fold.n_validation == len(validation)
        assert fold.n_test == len(test)


def test_walk_forward_config_infers_feature_timestamp_and_aliases_existing_split_key() -> None:
    df = pd.DataFrame(
        {
            "feature_timestamp": pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC"),
            "value": list(range(20)),
        }
    )

    config = resolve_walk_forward_config(df, {"calibration_test_size": 0.3})

    assert config.timestamp_column == "feature_timestamp"
    assert config.calibration_fraction == 0.3
