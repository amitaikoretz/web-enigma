from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.backtests.artifacts import (
    default_artifact_paths,
    hydrate_report_from_artifacts,
    inventory_backtest_artifacts,
    persist_backtest_report,
    summarize_backtest_artifacts,
    write_report_artifacts,
)
from app.backtests.persistence import BacktestArtifactPaths
from app.output.models import (
    BacktestReport,
    CandidateRecord,
    EquityPoint,
    OrderRecord,
    RejectionRecord,
    RunResult,
    RunSummary,
    TradeRecord,
)


def _sample_report() -> BacktestReport:
    return BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="abc",
        input_config={},
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="run-1",
                status="success",
                strategy="buy_and_hold",
                symbol="AAPL",
                data_source="csv",
                summary=RunSummary(
                    start_value=10000.0,
                    end_value=10500.0,
                    return_pct=5.0,
                ),
                candidates=[
                    CandidateRecord(
                        candidate_id="cand-1",
                        strategy_id="buy_and_hold",
                        symbol="AAPL",
                        timestamp="2024-01-02T00:00:00+00:00",
                        entry_price=100.0,
                        planned_stop_pct=0.02,
                        planned_horizon_bars=10,
                        was_traded=True,
                    )
                ],
                equity_curve=[
                    EquityPoint(datetime="2024-01-01T00:00:00+00:00", value=10000.0),
                    EquityPoint(datetime="2024-01-02T00:00:00+00:00", value=10500.0),
                ],
                orders=[
                    OrderRecord(
                        datetime="2024-01-02T00:00:00+00:00",
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
                        datetime="2024-01-03T00:00:00+00:00",
                        size=10.0,
                        price=105.0,
                        value=1050.0,
                        pnl=50.0,
                        pnlcomm=49.0,
                        reason="take_profit",
                    )
                ],
                rejections=[
                    RejectionRecord(
                        datetime="2024-01-02T00:00:00+00:00",
                        symbol="AAPL",
                        reason="max_positions",
                    )
                ],
            )
        ],
    )


def test_write_and_hydrate_report_artifacts(tmp_path: Path) -> None:
    report = _sample_report()
    paths = default_artifact_paths(tmp_path, "job-1")
    written = write_report_artifacts(report, paths=paths)

    assert written.candidates_parquet_path is not None
    assert written.equity_parquet_path is not None
    assert written.orders_parquet_path is not None
    assert written.trades_parquet_path is not None
    assert written.rejections_parquet_path is not None
    assert written.candidates_json_path is None
    assert Path(written.candidates_parquet_path).exists()
    assert Path(written.equity_parquet_path).exists()
    assert Path(written.orders_parquet_path).exists()
    assert Path(written.trades_parquet_path).exists()
    assert Path(written.rejections_parquet_path).exists()
    assert Path(written.report_parquet_path).exists()
    assert not Path(paths.candidates_json_path).exists()

    slim = report.model_copy(
        update={
            "results": [
                result.model_copy(
                    update={
                        "candidates": [],
                        "equity_curve": [],
                        "orders": [],
                        "trades": [],
                        "rejections": [],
                    }
                )
                for result in report.results
            ]
        }
    )
    hydrated = hydrate_report_from_artifacts(slim, paths=written)

    assert hydrated.results[0].candidates[0].candidate_id == "cand-1"
    assert len(hydrated.results[0].equity_curve) == 2
    assert hydrated.results[0].orders[0].price == 100.0
    assert hydrated.results[0].trades[0].reason == "take_profit"
    assert hydrated.results[0].rejections[0].reason == "max_positions"


def test_hydrate_report_from_shard_sidecars(tmp_path: Path) -> None:
    from app.backtests.sharding import ShardPlan, ShardSpec, write_shard_manifest

    run_id = "job-1:001:AAPL:breakout_channel"
    shard_output = tmp_path / "work" / "shards" / "aapl_breakout_channel.json"
    shard_output.parent.mkdir(parents=True, exist_ok=True)
    shard_output.write_text("{}", encoding="utf-8")

    orders_path = tmp_path / "work" / "shards" / "aapl_breakout_channel.orders.parquet"
    trades_path = tmp_path / "work" / "shards" / "aapl_breakout_channel.trades.parquet"
    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "datetime": "2024-01-02T16:40:00+00:00",
                "status": "Completed",
                "is_buy": True,
                "size": 1.0,
                "price": 100.0,
                "value": 100.0,
                "commission": 0.0,
            }
        ]
    ).to_parquet(orders_path, index=False)
    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "datetime": "2024-01-02T18:25:00+00:00",
                "size": 1.0,
                "price": 105.0,
                "value": 105.0,
                "pnl": 5.0,
                "pnlcomm": 5.0,
                "reason": "time_exit",
                "entry_datetime": "2024-01-02T16:40:00+00:00",
                "hold_minutes": 105.0,
                "hold_bars": 21,
            }
        ]
    ).to_parquet(trades_path, index=False)

    manifest_path = tmp_path / "work" / "manifest.json"
    write_shard_manifest(
        ShardPlan(
            split_by="symbol_strategy",
            config_path=str(tmp_path / "config.yaml"),
            shards=[
                ShardSpec(
                    shard_id="aapl_breakout_channel",
                    config_path=str(shard_output.with_suffix(".yaml")),
                    output_path=str(shard_output.resolve()),
                )
            ],
        ),
        manifest_path,
    )

    slim = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="abc",
        input_config={},
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id=run_id,
                status="success",
                strategy="breakout_channel",
                symbol="AAPL",
                data_source="alpaca",
                summary=RunSummary(start_value=10000.0, end_value=10005.0, return_pct=0.05),
            )
        ],
    )
    paths = BacktestArtifactPaths(
        report_json_path=str(tmp_path / "job-1.json"),
        manifest_path=str(manifest_path.resolve()),
        orders_parquet_path=str(tmp_path / "job-1.orders.parquet"),
        trades_parquet_path=str(tmp_path / "job-1.trades.parquet"),
    )

    hydrated = hydrate_report_from_artifacts(slim, paths=paths)

    assert len(hydrated.results[0].orders) == 1
    assert hydrated.results[0].orders[0].price == 100.0
    assert len(hydrated.results[0].trades) == 1
    assert hydrated.results[0].trades[0].reason == "time_exit"


def test_merge_persist_writes_combined_sidecars_from_shards(tmp_path: Path) -> None:
    from app.backtests.sharding import ShardPlan, ShardSpec, write_shard_manifest

    run_id = "job-1:001:AAPL:breakout_channel"
    work_dir = tmp_path / "work"
    shard_output = work_dir / "shards" / "aapl_breakout_channel.json"
    shard_output.parent.mkdir(parents=True, exist_ok=True)
    shard_output.write_text("{}", encoding="utf-8")

    orders_path = work_dir / "shards" / "aapl_breakout_channel.orders.parquet"
    trades_path = work_dir / "shards" / "aapl_breakout_channel.trades.parquet"
    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "datetime": "2024-01-02T16:40:00+00:00",
                "status": "Completed",
                "is_buy": True,
                "size": 1.0,
                "price": 100.0,
                "value": 100.0,
                "commission": 0.0,
            }
        ]
    ).to_parquet(orders_path, index=False)
    pd.DataFrame(
        [
            {
                "run_id": run_id,
                "datetime": "2024-01-02T18:25:00+00:00",
                "size": 1.0,
                "price": 105.0,
                "value": 105.0,
                "pnl": 5.0,
                "pnlcomm": 5.0,
                "reason": "time_exit",
                "entry_datetime": "2024-01-02T16:40:00+00:00",
                "hold_minutes": 105.0,
                "hold_bars": 21,
            }
        ]
    ).to_parquet(trades_path, index=False)

    manifest_path = work_dir / "manifest.json"
    write_shard_manifest(
        ShardPlan(
            split_by="symbol_strategy",
            config_path=str(work_dir / "config.yaml"),
            shards=[
                ShardSpec(
                    shard_id="aapl_breakout_channel",
                    config_path=str(shard_output.with_suffix(".yaml")),
                    output_path=str(shard_output.resolve()),
                )
            ],
        ),
        manifest_path,
    )

    merged = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="abc",
        input_config={},
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id=run_id,
                status="success",
                strategy="breakout_channel",
                symbol="AAPL",
                data_source="alpaca",
                summary=RunSummary(start_value=10000.0, end_value=10005.0, return_pct=0.05),
            )
        ],
    )
    output_path = tmp_path / "shared-results" / "job-1.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    written = persist_backtest_report(merged, output_path, manifest_path=manifest_path)

    artifact_dir = output_path.parent / "job-1"
    assert written.orders_parquet_path == str((artifact_dir / "job-1.orders.parquet").resolve())
    assert written.trades_parquet_path == str((artifact_dir / "job-1.trades.parquet").resolve())
    assert Path(written.orders_parquet_path).exists()
    assert Path(written.trades_parquet_path).exists()
    orders = pd.read_parquet(written.orders_parquet_path)
    trades = pd.read_parquet(written.trades_parquet_path)
    assert len(orders) == 1
    assert len(trades) == 1
    assert orders.iloc[0]["run_id"] == run_id
    assert trades.iloc[0]["reason"] == "time_exit"


def test_persist_backtest_report_writes_slim_json_and_sidecars(tmp_path: Path) -> None:
    report = _sample_report()
    output_path = tmp_path / "job-1.json"
    written = persist_backtest_report(report, output_path)

    import json

    raw = json.loads(output_path.read_text(encoding="utf-8"))
    result = raw["results"][0]
    assert "equity_curve" not in result
    assert "candidates" not in result
    assert "orders" not in result
    assert "trades" not in result
    assert "rejections" not in result
    assert written.orders_parquet_path is not None
    assert Path(written.orders_parquet_path).exists()


def test_summarize_backtest_artifacts_returns_compact_entries(tmp_path: Path) -> None:
    report = _sample_report()
    output_path = tmp_path / "job-1" / "job-1.json"
    persist_backtest_report(report, output_path)

    summary = summarize_backtest_artifacts("job-1", tmp_path)

    kinds = {entry.kind for entry in summary}
    assert "orders_parquet" in kinds
    assert "trades_parquet" in kinds
    assert all(hasattr(entry, "kind") and not hasattr(entry, "path") for entry in summary)


def test_inventory_backtest_artifacts_lists_existing_sidecars(tmp_path: Path) -> None:
    report = _sample_report()
    output_path = tmp_path / "job-1" / "job-1.json"
    persist_backtest_report(report, output_path)
    (tmp_path / "job-1" / "job-1.yaml").write_text("runs: []\n", encoding="utf-8")

    inventory = inventory_backtest_artifacts("job-1", tmp_path)

    kinds = {entry.kind for entry in inventory}
    assert "report_json" in kinds
    assert "config" in kinds
    assert "orders_parquet" in kinds
    assert "trades_parquet" in kinds
    assert "candidates_parquet" in kinds
    assert all(entry.size_bytes is not None and entry.size_bytes > 0 for entry in inventory)
