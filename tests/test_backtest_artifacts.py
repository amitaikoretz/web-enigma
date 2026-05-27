from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.backtests.artifacts import (
    default_artifact_paths,
    hydrate_report_from_artifacts,
    persist_backtest_report,
    write_report_artifacts,
)
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
