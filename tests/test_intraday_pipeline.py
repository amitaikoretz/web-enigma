from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.config.models import CsvDataSource, DataCacheConfig
from app.intraday.models import (
    IntradayCostConfig,
    IntradayDatasetManifest,
    IntradayRunConfig,
    IntradaySeriesSpec,
    IntradaySizingConfig,
    IntradayUniverseConfig,
    IntradayWalkForwardConfig,
    IntradayModelSearchConfig,
)
from app.intraday.pipeline import run_intraday_pipeline, write_intraday_artifacts


def _write_csv(path: Path, *, offset: float = 0.0) -> None:
    index = pd.date_range("2024-01-01", periods=160, freq="D", tz="UTC")
    rows = []
    for i, ts in enumerate(index):
        close = 100.0 + offset + i * 0.5
        rows.append(
            {
                "datetime": ts.isoformat(),
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.5,
                "close": close,
                "volume": 10_000 + i * 20,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def test_intraday_pipeline_writes_deterministic_artifacts(tmp_path: Path) -> None:
    aapl = tmp_path / "aapl.csv"
    msft = tmp_path / "msft.csv"
    spy = tmp_path / "spy.csv"
    _write_csv(aapl, offset=0.0)
    _write_csv(msft, offset=5.0)
    _write_csv(spy, offset=2.0)

    config = IntradayRunConfig(
        model_version="intraday_model_v1",
        feature_version="intraday_features_v1",
        label_version="intraday_labels_v1",
        dataset_version="intraday_dataset_v1",
        output_dir=str(tmp_path / "out"),
        allow_short=True,
        lookback_bars=20,
        horizon_bars=5,
        data_cache=DataCacheConfig(enabled=False, directory=str(tmp_path / "cache")),
        universe=IntradayUniverseConfig(
            start_date=pd.Timestamp("2024-01-01").date(),
            end_date=pd.Timestamp("2024-06-08").date(),
            interval="1d",
            symbols=[
                IntradaySeriesSpec(symbol="AAPL", data=CsvDataSource(type="csv", path=str(aapl))),
                IntradaySeriesSpec(symbol="MSFT", data=CsvDataSource(type="csv", path=str(msft))),
            ],
            benchmark=IntradaySeriesSpec(symbol="SPY", data=CsvDataSource(type="csv", path=str(spy))),
        ),
        walk_forward=IntradayWalkForwardConfig(
            train_days=30,
            validation_days=5,
            test_days=5,
            step_days=5,
            embargo_bars=1,
            min_train_rows=40,
            min_validation_rows=10,
            min_test_rows=10,
        ),
        model_search=IntradayModelSearchConfig(
            alpha_grid=[0.1, 1.0],
            threshold_bps_grid=[1.0, 2.5],
            target_edge_bps_grid=[5.0, 10.0],
            max_risk_fraction_grid=[0.0005, 0.001],
        ),
        costs=IntradayCostConfig(spread_bps=1.0, slippage_bps=1.0, impact_bps=0.5),
        sizing=IntradaySizingConfig(
            account_equity=100000.0,
            max_participation_rate=0.02,
            max_notional_fraction=0.02,
            target_vol_bps=20.0,
            floor_vol_bps=5.0,
            stop_vol_multiplier=1.5,
            min_stop_bps=5.0,
        ),
    )

    result = run_intraday_pipeline(config)
    paths = write_intraday_artifacts(result, tmp_path / "artifacts")

    for path in paths.values():
        assert path.exists()

    manifest = json.loads(paths["manifest"].read_text(encoding="utf-8"))
    assert manifest["dataset_version"] == "intraday_dataset_v1"
    assert manifest["feature_version"] == "intraday_features_v1"

    predictions = pd.read_parquet(paths["predictions"])
    positions = pd.read_parquet(paths["positions"])
    assert not predictions.empty
    assert not positions.empty
    assert {"pred_return_pct", "net_pnl", "fold_id", "subset"}.issubset(predictions.columns)
    assert {"final_shares", "threshold_bps", "quality_scale"}.issubset(positions.columns)

    rerun = run_intraday_pipeline(config)
    assert rerun["metrics"].aggregate == result["metrics"].aggregate
    assert rerun["metrics"].selected_hyperparameters == result["metrics"].selected_hyperparameters
