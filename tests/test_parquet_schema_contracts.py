from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest
from pandas.api.types import is_bool_dtype, is_numeric_dtype
from pydantic import ValidationError

from app.backtests.artifacts import persist_backtest_report, load_labels_from_parquet, load_rejections_from_parquet
from app.config.models import CsvDataSource, DataCacheConfig
from app.datasets.models import DatasetParquetRow
from app.data.cache import CacheKey, ParquetDataCache
from app.intraday.features import FEATURE_COLUMNS
from app.intraday.models import (
    IntradayCostConfig,
    IntradayModelSearchConfig,
    IntradayRunConfig,
    IntradaySeriesSpec,
    IntradaySizingConfig,
    IntradayUniverseConfig,
    IntradayWalkForwardConfig,
)
from app.intraday.pipeline import run_intraday_pipeline, write_intraday_artifacts
from app.output.models import (
    BacktestReport,
    CandidateRecord,
    EquityPoint,
    FeatureSnapshotRecord,
    OrderRecord,
    OutcomeLabelRecord,
    RejectionRecord,
    RunResult,
    RunSummary,
    TradeRecord,
)
from app.risk.dataset.builder import build_risk_dataset
from app.risk.models import RiskDatasetConfig


DOC_PATH = Path("docs/parquet-schema-contracts.md")


def _sample_backtest_report() -> BacktestReport:
    candidate = CandidateRecord(
        candidate_id="cand-1",
        strategy_id="breakout_channel",
        symbol="AAPL",
        timestamp="2024-01-02T15:30:00+00:00",
        entry_price=100.0,
        planned_stop_pct=0.02,
        planned_target_pct=0.04,
        planned_horizon_bars=5,
        signal_score=0.8,
        signal_reason="breakout confirmed",
        metadata={"source_tag": "alpha", "note": "ignored"},
        was_traded=True,
        reject_reason=None,
    )
    run = RunResult(
        run_id="job-1",
        name="sample run",
        status="success",
        strategy="breakout_channel",
        symbol="AAPL",
        data_source="csv",
        summary=RunSummary(
            start_value=10_000.0,
            end_value=10_250.0,
            return_pct=2.5,
            max_drawdown_pct=-1.0,
            sharpe_ratio=1.2,
            total_trades=1,
            won_trades=1,
            lost_trades=0,
        ),
        orders=[
            OrderRecord(
                datetime="2024-01-02T15:31:00+00:00",
                status="Completed",
                is_buy=True,
                size=10.0,
                price=100.0,
                value=1000.0,
                commission=1.0,
            )
        ],
        trades=[
            TradeRecord(
                datetime="2024-01-03T15:31:00+00:00",
                entry_bar_index=1,
                exit_bar_index=3,
                size=10.0,
                price=104.0,
                value=1040.0,
                pnl=40.0,
                pnlcomm=39.0,
                reason="take_profit",
                entry_datetime="2024-01-02T15:31:00+00:00",
                hold_minutes=390.0,
                hold_bars=3,
                regime_label="trend",
            )
        ],
        rejections=[
            RejectionRecord(
                datetime="2024-01-02T15:30:00+00:00",
                symbol="AAPL",
                reason="max_positions",
            )
        ],
        candidates=[candidate],
        equity_curve=[
            EquityPoint(datetime="2024-01-02T15:31:00+00:00", value=10_000.0),
            EquityPoint(datetime="2024-01-03T15:31:00+00:00", value=10_250.0),
        ],
    )
    return BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="abc123",
        input_config={
            "runs": [
                {
                    "run_id": "job-1",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-03",
                    "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                    "strategy": "breakout_channel",
                    "strategy_params": {
                        "lookback": 3,
                        "stake": 1.0,
                        "stop_loss_pct": 0.02,
                        "take_profit_pct": 0.04,
                        "max_hold_bars": 5,
                    },
                    "analyzers": {"include_candidate_log": True},
                }
            ]
        },
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[run],
    )


def _sample_label() -> OutcomeLabelRecord:
    return OutcomeLabelRecord(
        candidate_id="cand-1",
        label_version="labels_v1",
        entry_price=100.0,
        horizon_bars=5,
        stop_pct=0.02,
        target_pct=0.04,
        mae_pct=-0.01,
        mae_abs_pct=0.01,
        mae_atr=0.5,
        mfe_pct=0.04,
        final_return_pct=0.03,
        realized_R=1.5,
        hit_stop=False,
        hit_target=True,
        hit_stop_before_target=False,
        bars_to_stop=None,
        bars_to_target=3,
        bars_held=3,
        exit_reason="TARGET",
        label_quality_flag="OK",
    )


def _sample_feature() -> FeatureSnapshotRecord:
    return FeatureSnapshotRecord(
        candidate_id="cand-1",
        feature_version="features_v1",
        feature_timestamp="2024-01-02T15:30:00+00:00",
        feature_quality_flag="OK",
        return_5=0.02,
        return_10=0.03,
        return_20=0.04,
        trend_slope_20=0.001,
        trend_slope_50=0.002,
        sma_20_distance=0.01,
        sma_50_distance=0.02,
        rsi_14=60.0,
        return_zscore_20=1.2,
        gap_pct=0.001,
        consecutive_up_bars=4,
        volume_zscore_20=0.8,
        relative_volume_20=1.4,
        atr_14_pct=0.02,
        realized_vol_10=0.01,
        realized_vol_20=0.02,
        vol_percentile_60=0.75,
        atr_expansion_10_50=1.1,
        dollar_volume_20=1_250_000.0,
        volume_percentile_60=0.7,
        index_return_20=0.015,
        index_trend_slope_50=0.0005,
        correlation_to_index_60=0.85,
        beta_to_index_60=1.1,
        metadata_features={"meta_source_tag": "alpha"},
    )


def _write_sample_backtest_artifacts(tmp_path: Path) -> tuple[Path, BacktestArtifactPaths]:
    report = _sample_backtest_report()
    output_path = tmp_path / "backtests" / "job-1.json"
    written = persist_backtest_report(
        report,
        output_path,
        risk_auxiliary_by_run={
            "job-1": ([_sample_label()], [_sample_feature()]),
        },
    )
    assert written.labels_parquet_path is not None
    assert written.features_parquet_path is not None
    return output_path, written


def test_contract_docs_cover_every_parquet_family() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")
    expected_headings = [
        "Backtest Report Summary Parquet",
        "Backtest Candidates Parquet",
        "Backtest Orders Parquet",
        "Backtest Trades Parquet",
        "Backtest Rejections Parquet",
        "Backtest Equity Parquet",
        "Risk Labels Parquet",
        "Risk Features Parquet",
        "Joined Risk Dataset Parquet",
        "Dataset Download Parquet",
        "Intraday Dataset Parquet",
        "Intraday Predictions Parquet",
        "Intraday Positions Parquet",
        "Parquet Cache Files",
    ]
    for heading in expected_headings:
        assert f"## {heading}" in text


def test_backtest_sidecar_schemas_round_trip(tmp_path: Path) -> None:
    report = _sample_backtest_report()
    _, written = _write_sample_backtest_artifacts(tmp_path)

    report_df = pd.read_parquet(written.report_parquet_path)
    candidates_df = pd.read_parquet(written.candidates_parquet_path)
    orders_df = pd.read_parquet(written.orders_parquet_path)
    trades_df = pd.read_parquet(written.trades_parquet_path)
    rejections_df = pd.read_parquet(written.rejections_parquet_path)
    equity_df = pd.read_parquet(written.equity_parquet_path)
    labels_df = pd.read_parquet(written.labels_parquet_path)
    features_df = pd.read_parquet(written.features_parquet_path)

    assert set(report_df.columns) == {
        "run_id",
        "name",
        "status",
        "strategy",
        "symbol",
        "data_source",
        "start_value",
        "end_value",
        "return_pct",
        "max_drawdown_pct",
        "sharpe_ratio",
        "total_trades",
        "won_trades",
        "lost_trades",
    }
    assert set(candidates_df.columns) == {
        "run_id",
        "candidate_id",
        "strategy_id",
        "symbol",
        "timestamp",
        "side",
        "entry_price",
        "entry_type",
        "planned_stop_pct",
        "planned_target_pct",
        "planned_horizon_bars",
        "signal_score",
        "signal_reason",
        "metadata_json",
        "was_traded",
        "reject_reason",
    }
    assert set(orders_df.columns) == {
        "run_id",
        "datetime",
        "status",
        "is_buy",
        "size",
        "price",
        "value",
        "commission",
    }
    assert set(trades_df.columns) == {
        "run_id",
        "datetime",
        "entry_bar_index",
        "exit_bar_index",
        "size",
        "price",
        "value",
        "pnl",
        "pnlcomm",
        "reason",
        "entry_datetime",
        "hold_minutes",
        "hold_bars",
        "regime_label",
    }
    assert set(rejections_df.columns) == {
        "run_id",
        "datetime",
        "symbol",
        "reason",
    }
    assert set(equity_df.columns) == {"run_id", "datetime", "value"}
    assert set(labels_df.columns) == {
        "run_id",
        "candidate_id",
        "label_version",
        "entry_price",
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
    }
    assert set(features_df.columns) == {
        "run_id",
        "candidate_id",
        "feature_version",
        "feature_timestamp",
        "feature_quality_flag",
        "return_5",
        "return_10",
        "return_20",
        "trend_slope_20",
        "trend_slope_50",
        "sma_20_distance",
        "sma_50_distance",
        "rsi_14",
        "return_zscore_20",
        "gap_pct",
        "consecutive_up_bars",
        "volume_zscore_20",
        "relative_volume_20",
        "atr_14_pct",
        "realized_vol_10",
        "realized_vol_20",
        "vol_percentile_60",
        "atr_expansion_10_50",
        "dollar_volume_20",
        "volume_percentile_60",
        "index_return_20",
        "index_trend_slope_50",
        "correlation_to_index_60",
        "beta_to_index_60",
        "metadata_features_json",
    }


def test_rejection_parquet_missing_symbol_does_not_crash(tmp_path: Path) -> None:
    path = tmp_path / "rejections.parquet"
    pd.DataFrame(
        [
            {
                "run_id": "run-1",
                "datetime": "2024-01-02T15:30:00+00:00",
                "symbol": None,
                "reason": "weak_close",
            }
        ]
    ).to_parquet(path, index=False)

    loaded = load_rejections_from_parquet(path)

    assert list(loaded) == ["run-1"]
    assert len(loaded["run-1"]) == 1
    assert loaded["run-1"][0].symbol is None
    assert loaded["run-1"][0].reason == "weak_close"


def test_risk_dataset_schema_matches_component_contracts(tmp_path: Path) -> None:
    _write_sample_backtest_artifacts(tmp_path)
    output_path = tmp_path / "risk_dataset.parquet"
    manifest = build_risk_dataset(
        [tmp_path / "backtests" / "job-1.json"],
        output_path=output_path,
        config=RiskDatasetConfig(include_index_features=False),
    )

    assert manifest.joined_rows == 1
    df = pd.read_parquet(output_path)
    assert {
        "dataset_version",
        "label_version",
        "feature_version",
        "candidate_id",
        "symbol",
        "entry_price",
        "planned_stop_pct",
        "planned_horizon_bars",
        "stop_pct",
        "feature_quality_flag",
        "meta_source_tag",
    }.issubset(df.columns)
    assert isinstance(df["symbol"].dtype, pd.CategoricalDtype)
    assert is_numeric_dtype(df["entry_price"])
    assert is_numeric_dtype(df["stop_pct"])
    assert df.loc[0, "meta_source_tag"] == "alpha"


def _write_intraday_csv(path: Path, *, offset: float = 0.0) -> None:
    index = pd.date_range("2024-01-01", periods=140, freq="D", tz="UTC")
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


def test_intraday_artifact_schemas_round_trip(tmp_path: Path) -> None:
    aapl = tmp_path / "aapl.csv"
    msft = tmp_path / "msft.csv"
    spy = tmp_path / "spy.csv"
    _write_intraday_csv(aapl, offset=0.0)
    _write_intraday_csv(msft, offset=5.0)
    _write_intraday_csv(spy, offset=2.0)

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
            end_date=pd.Timestamp("2024-05-19").date(),
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

    dataset = pd.read_parquet(paths["dataset"])
    predictions = pd.read_parquet(paths["predictions"])
    positions = pd.read_parquet(paths["positions"])

    assert {"symbol", "timestamp", "entry_price", "target_return_pct", "target_return_bps", "feature_quality_flag"}.issubset(
        dataset.columns
    )
    assert set(FEATURE_COLUMNS).issubset(dataset.columns)
    assert {"fold_id", "subset", "pred_return_pct", "expected_edge_bps", "net_pnl", "hit_direction"}.issubset(
        predictions.columns
    )
    assert {
        "symbol",
        "timestamp",
        "direction",
        "expected_edge_bps",
        "forecast_risk_bps",
        "threshold_bps",
        "quality_scale",
        "vol_scale",
        "risk_based_shares",
        "liquidity_cap_shares",
        "final_shares",
        "final_notional",
        "entry_price",
        "stop_distance_bps",
        "roundtrip_cost_bps",
    }.issubset(positions.columns)
    assert is_numeric_dtype(dataset["entry_price"])
    assert is_numeric_dtype(predictions["pred_return_pct"])
    assert is_numeric_dtype(positions["final_shares"])


def test_dataset_download_parquet_schema_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.standalone import datasets_download_argo as module

    frame = pd.DataFrame(
        {
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.5],
            "Close": [100.5],
            "Volume": [1_000.0],
        },
        index=pd.DatetimeIndex([pd.Timestamp("2026-06-01T14:30:00Z")], name="datetime"),
    )
    monkeypatch.setattr(module, "build_alpaca_data_feed_with_cache", lambda *args, **kwargs: (frame, "miss"))
    monkeypatch.setattr(module, "build_alpaca_options_data_feed_with_cache", lambda *args, **kwargs: (frame, "miss"))

    module.main(
        symbol="AAPL",
        provider="alpaca",
        resolution="5m",
        start_date=date(2026, 5, 8).isoformat(),
        end_date=date(2026, 6, 7).isoformat(),
        options_enabled=True,
        options_feed="indicative",
        output_dir=str(tmp_path),
        terminal_command_out=str(tmp_path / "terminal-command.txt"),
        dataset_path_out=str(tmp_path / "dataset-path.txt"),
        manifest_path_out=str(tmp_path / "manifest-path.txt"),
        options_dataset_path_out=str(tmp_path / "options-dataset-path.txt"),
        options_manifest_path_out=str(tmp_path / "options-manifest-path.txt"),
    )

    dataset_df = pd.read_parquet(tmp_path / "AAPL-alpaca-5m.parquet")
    options_df = pd.read_parquet(tmp_path / "AAPL-alpaca-options-5m.parquet")

    assert DatasetParquetRow.model_validate(dataset_df.iloc[0].to_dict())
    assert DatasetParquetRow.model_validate(options_df.iloc[0].to_dict())


def test_parquet_cache_round_trip_preserves_source_frame(tmp_path: Path) -> None:
    cache = ParquetDataCache(tmp_path / "cache")
    key = CacheKey(
        source="yahoo",
        symbol="AAPL",
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-05",
    )
    frame = pd.DataFrame(
        {"open": [100.0, 101.0], "close": [101.0, 102.0]},
        index=pd.Index(pd.date_range("2024-01-01", periods=2, freq="D", tz="UTC"), name="timestamp"),
    )

    path = cache.put(key, frame)
    read = cache.get(key, max_age=pd.Timedelta(days=1))

    assert path.exists()
    assert read.status == "hit"
    pd.testing.assert_frame_equal(frame, read.frame, check_freq=False)


def test_missing_required_schema_column_fails_validation(tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.labels.parquet"
    pd.DataFrame(
        [
            {
                "run_id": "job-1",
                "label_version": "labels_v1",
                "entry_price": 100.0,
            }
        ]
    ).to_parquet(bad_path, index=False)

    with pytest.raises(ValidationError):
        load_labels_from_parquet(bad_path)
