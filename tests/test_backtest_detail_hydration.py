from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.backtests.artifacts import default_artifact_paths, write_report_artifacts
from app.backtests.models import BacktestListItem
from app.backtests.service import BacktestArtifactStore, BacktestJobService
from app.output.models import BacktestReport, RunResult, RunSummary, TradeRecord


class _FakeJobRepository:
    def __init__(self, metadata: BacktestListItem):
        self._metadata = metadata

    def get(self, backtest_id: str):
        return self._metadata if backtest_id == self._metadata.id else None

    def get_paths(self, backtest_id: str):
        return None


class _MissingJobRepository:
    def get(self, backtest_id: str):
        return None

    def get_paths(self, backtest_id: str):
        return None


def test_get_detail_hydrates_trades_without_db_paths(tmp_path: Path) -> None:
    backtest_id = "bt1"
    now = datetime.now(UTC)
    report = BacktestReport(
        generated_at=now,
        app_version="test",
        config_sha256="abc",
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="r1",
                name="run1",
                status="success",
                strategy="sma_cross",
                symbol="AAPL",
                data_source="csv",
                summary=RunSummary(
                    start_value=10000.0,
                    end_value=10010.0,
                    return_pct=0.1,
                    max_drawdown_pct=0.0,
                    sharpe_ratio=None,
                    total_trades=1,
                    won_trades=1,
                    lost_trades=0,
                ),
                trades=[
                    TradeRecord(
                        datetime=now.isoformat(),
                        size=1.0,
                        price=100.0,
                        value=100.0,
                        pnl=10.0,
                        pnlcomm=10.0,
                        reason="exit:test",
                    )
                ],
            )
        ],
    )

    repository = BacktestArtifactStore(tmp_path)
    repository.ensure_ready()
    repository.save_report(backtest_id, report)

    paths = default_artifact_paths(repository.output_dir, backtest_id)
    write_report_artifacts(report, paths=paths)

    metadata = BacktestListItem(
        id=backtest_id,
        created_at=now,
        updated_at=now,
        status="completed",
        total_runs=1,
    )
    service = BacktestJobService(
        repository=repository,
        job_repository=_FakeJobRepository(metadata),  # type: ignore[arg-type]
    )

    detail = service.get_detail(backtest_id)
    assert detail is not None
    assert detail.report is not None
    assert detail.report.results[0].trades, "expected trades to be hydrated from sidecar parquet"


def test_get_detail_hydrates_trades_when_manifest_path_is_missing(tmp_path: Path) -> None:
    backtest_id = "bt1"
    now = datetime.now(UTC)
    report = BacktestReport(
        generated_at=now,
        app_version="test",
        config_sha256="abc",
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="r1",
                name="run1",
                status="success",
                strategy="sma_cross",
                symbol="AAPL",
                data_source="csv",
                summary=RunSummary(
                    start_value=10000.0,
                    end_value=10010.0,
                    return_pct=0.1,
                    max_drawdown_pct=0.0,
                    sharpe_ratio=None,
                    total_trades=1,
                    won_trades=1,
                    lost_trades=0,
                ),
                trades=[
                    TradeRecord(
                        datetime=now.isoformat(),
                        size=1.0,
                        price=100.0,
                        value=100.0,
                        pnl=10.0,
                        pnlcomm=10.0,
                        reason="exit:test",
                    )
                ],
            )
        ],
    )

    repository = BacktestArtifactStore(tmp_path)
    repository.ensure_ready()
    repository.save_report(backtest_id, report)

    paths = default_artifact_paths(repository.output_dir, backtest_id)
    write_report_artifacts(report, paths=paths)

    metadata = BacktestListItem(
        id=backtest_id,
        created_at=now,
        updated_at=now,
        status="completed",
        total_runs=1,
    )
    service = BacktestJobService(
        repository=repository,
        job_repository=_FakeJobRepository(metadata),  # type: ignore[arg-type]
    )

    detail = service.get_detail(backtest_id)
    assert detail is not None
    assert detail.report is not None
    assert detail.report.results[0].trades, "expected trades to be hydrated even without stored manifest_path"


def test_get_detail_hydrates_trades_when_sidecar_path_metadata_is_partial(tmp_path: Path) -> None:
    backtest_id = "bt1"
    now = datetime.now(UTC)
    report = BacktestReport(
        generated_at=now,
        app_version="test",
        config_sha256="abc",
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="r1",
                name="run1",
                status="success",
                strategy="sma_cross",
                symbol="AAPL",
                data_source="csv",
                summary=RunSummary(
                    start_value=10000.0,
                    end_value=10010.0,
                    return_pct=0.1,
                    max_drawdown_pct=0.0,
                    sharpe_ratio=None,
                    total_trades=1,
                    won_trades=1,
                    lost_trades=0,
                ),
                trades=[
                    TradeRecord(
                        datetime=now.isoformat(),
                        size=1.0,
                        price=100.0,
                        value=100.0,
                        pnl=10.0,
                        pnlcomm=10.0,
                        reason="exit:test",
                    )
                ],
            )
        ],
    )

    repository = BacktestArtifactStore(tmp_path)
    repository.ensure_ready()
    repository.save_report(backtest_id, report)

    paths = default_artifact_paths(repository.output_dir, backtest_id)
    write_report_artifacts(report, paths=paths)

    metadata = BacktestListItem(
        id=backtest_id,
        created_at=now,
        updated_at=now,
        status="completed",
        total_runs=1,
    )
    service = BacktestJobService(
        repository=repository,
        job_repository=_FakeJobRepository(metadata),  # type: ignore[arg-type]
    )

    # Simulate an older DB row that knows the report path but is missing the sidecar paths.
    service.job_repository.get_paths = lambda backtest_id: type(  # type: ignore[method-assign]
        "PartialPaths",
        (),
        {
            "config_path": None,
            "report_json_path": str(repository.report_path(backtest_id)),
            "report_parquet_path": None,
            "candidates_json_path": None,
            "candidates_parquet_path": None,
            "equity_parquet_path": None,
            "orders_parquet_path": None,
            "trades_parquet_path": None,
            "rejections_parquet_path": None,
            "labels_parquet_path": None,
            "features_parquet_path": None,
            "manifest_path": str((repository.output_dir / backtest_id / "manifest.json").resolve()),
        },
    )()

    detail = service.get_detail(backtest_id)
    assert detail is not None
    assert detail.report is not None
    assert detail.report.results[0].trades, "expected trades to be hydrated from fallback artifact paths"


def test_get_detail_hydrates_trades_when_db_paths_point_elsewhere(tmp_path: Path) -> None:
    backtest_id = "bt1"
    now = datetime.now(UTC)
    report = BacktestReport(
        generated_at=now,
        app_version="test",
        config_sha256="abc",
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="r1",
                name="run1",
                status="success",
                strategy="sma_cross",
                symbol="AAPL",
                data_source="csv",
                summary=RunSummary(
                    start_value=10000.0,
                    end_value=10010.0,
                    return_pct=0.1,
                    max_drawdown_pct=0.0,
                    sharpe_ratio=None,
                    total_trades=1,
                    won_trades=1,
                    lost_trades=0,
                ),
                trades=[
                    TradeRecord(
                        datetime=now.isoformat(),
                        size=1.0,
                        price=100.0,
                        value=100.0,
                        pnl=10.0,
                        pnlcomm=10.0,
                        reason="exit:test",
                    )
                ],
            )
        ],
    )

    repository = BacktestArtifactStore(tmp_path)
    repository.ensure_ready()
    repository.save_report(backtest_id, report)

    paths = default_artifact_paths(repository.output_dir, backtest_id)
    write_report_artifacts(report, paths=paths)

    metadata = BacktestListItem(
        id=backtest_id,
        created_at=now,
        updated_at=now,
        status="completed",
        total_runs=1,
    )
    service = BacktestJobService(
        repository=repository,
        job_repository=_FakeJobRepository(metadata),  # type: ignore[arg-type]
    )

    service.job_repository.get_paths = lambda backtest_id: type(  # type: ignore[method-assign]
        "WrongRootPaths",
        (),
        {
            "config_path": "/data/backtest-results/bt1/bt1.yaml",
            "report_json_path": str(repository.report_path(backtest_id)),
            "report_parquet_path": "/data/backtest-results/bt1/bt1.parquet",
            "candidates_json_path": "/data/backtest-results/bt1/bt1.candidates.json",
            "candidates_parquet_path": "/data/backtest-results/bt1/bt1.candidates.parquet",
            "equity_parquet_path": "/data/backtest-results/bt1/bt1.equity.parquet",
            "orders_parquet_path": "/data/backtest-results/bt1/bt1.orders.parquet",
            "trades_parquet_path": "/data/backtest-results/bt1/bt1.trades.parquet",
            "rejections_parquet_path": "/data/backtest-results/bt1/bt1.rejections.parquet",
            "labels_parquet_path": "/data/backtest-results/bt1/bt1.labels.parquet",
            "features_parquet_path": "/data/backtest-results/bt1/bt1.features.parquet",
            "manifest_path": "/data/backtest-results/bt1/manifest.json",
        },
    )()

    detail = service.get_detail(backtest_id)
    assert detail is not None
    assert detail.report is not None
    assert detail.report.results[0].trades, "expected trades to fall back to the accessible local artifact paths"


def test_get_detail_recovers_from_missing_database_row(tmp_path: Path) -> None:
    backtest_id = "bt1"
    now = datetime.now(UTC)
    report = BacktestReport(
        generated_at=now,
        app_version="test",
        config_sha256="abc",
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        input_config={
            "runs": [
                {
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-02",
                    "data": {"symbol": "AAPL", "interval": "5m", "feed": "iex"},
                    "trigger": {"name": "volume_rally"},
                    "exit_rules": [{"type": "atr_stop"}],
                }
            ]
        },
        results=[
            RunResult(
                run_id="r1",
                name="run1",
                status="success",
                strategy="sma_cross",
                symbol="AAPL",
                data_source="csv",
                summary=RunSummary(
                    start_value=10000.0,
                    end_value=10010.0,
                    return_pct=0.1,
                    max_drawdown_pct=0.0,
                    sharpe_ratio=None,
                    total_trades=1,
                    won_trades=1,
                    lost_trades=0,
                ),
            )
        ],
    )

    repository = BacktestArtifactStore(tmp_path)
    repository.ensure_ready()
    repository.save_report(backtest_id, report)

    service = BacktestJobService(
        repository=repository,
        job_repository=_MissingJobRepository(),  # type: ignore[arg-type]
    )

    detail = service.get_detail(backtest_id)
    assert detail is not None
    assert detail.metadata.id == backtest_id
    assert detail.metadata.status == "completed"
    assert detail.report is not None
    assert detail.report.results[0].run_id == "r1"
