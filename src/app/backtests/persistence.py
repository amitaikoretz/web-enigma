from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.backtests.models import BacktestListItem, BacktestSelectionSummary
from app.db.models import BacktestJob


@dataclass(frozen=True)
class BacktestArtifactPaths:
    config_path: str | None = None
    report_json_path: str | None = None
    report_parquet_path: str | None = None
    candidates_json_path: str | None = None
    candidates_parquet_path: str | None = None
    equity_parquet_path: str | None = None
    orders_parquet_path: str | None = None
    trades_parquet_path: str | None = None
    rejections_parquet_path: str | None = None
    manifest_path: str | None = None


def _selection_to_dict(selection: BacktestSelectionSummary | None) -> dict | None:
    if selection is None:
        return None
    return selection.model_dump(mode="json")


def _selection_from_dict(raw: dict | None) -> BacktestSelectionSummary | None:
    if raw is None:
        return None
    return BacktestSelectionSummary.model_validate(raw)


def _paths_from_row(row: BacktestJob) -> BacktestArtifactPaths:
    return BacktestArtifactPaths(
        config_path=row.config_path,
        report_json_path=row.report_json_path,
        report_parquet_path=row.report_parquet_path,
        candidates_json_path=row.candidates_json_path,
        candidates_parquet_path=row.candidates_parquet_path,
        equity_parquet_path=row.equity_parquet_path,
        orders_parquet_path=row.orders_parquet_path,
        trades_parquet_path=row.trades_parquet_path,
        rejections_parquet_path=row.rejections_parquet_path,
        manifest_path=row.manifest_path,
    )


def _row_to_list_item(row: BacktestJob) -> BacktestListItem:
    return BacktestListItem(
        id=row.id,
        created_at=row.created_at,
        updated_at=row.updated_at,
        status=row.status,  # type: ignore[arg-type]
        report_status=row.report_status,  # type: ignore[arg-type]
        total_runs=row.total_runs,
        completed_runs=row.completed_runs,
        successful_runs=row.successful_runs,
        failed_runs=row.failed_runs,
        selection=_selection_from_dict(row.selection),
        error_message=row.error_message,
        execution_backend=row.execution_backend,  # type: ignore[arg-type]
        workflow_name=row.workflow_name,
        workflow_namespace=row.workflow_namespace,
        started_at=row.started_at,
        finished_at=row.finished_at,
    )


def _apply_list_item(row: BacktestJob, item: BacktestListItem) -> None:
    row.updated_at = item.updated_at
    row.status = item.status
    row.report_status = item.report_status
    row.total_runs = item.total_runs
    row.completed_runs = item.completed_runs
    row.successful_runs = item.successful_runs
    row.failed_runs = item.failed_runs
    row.selection = _selection_to_dict(item.selection)
    row.error_message = item.error_message
    row.execution_backend = item.execution_backend
    row.workflow_name = item.workflow_name
    row.workflow_namespace = item.workflow_namespace
    row.started_at = item.started_at
    row.finished_at = item.finished_at


class SqlAlchemyBacktestJobRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def create(self, item: BacktestListItem, *, paths: BacktestArtifactPaths | None = None) -> None:
        resolved_paths = paths or BacktestArtifactPaths()
        with self._session_factory() as session:
            row = BacktestJob(
                id=item.id,
                created_at=item.created_at,
                updated_at=item.updated_at,
                status=item.status,
                report_status=item.report_status,
                total_runs=item.total_runs,
                completed_runs=item.completed_runs,
                successful_runs=item.successful_runs,
                failed_runs=item.failed_runs,
                selection=_selection_to_dict(item.selection),
                error_message=item.error_message,
                execution_backend=item.execution_backend,
                workflow_name=item.workflow_name,
                workflow_namespace=item.workflow_namespace,
                started_at=item.started_at,
                finished_at=item.finished_at,
                config_path=resolved_paths.config_path,
                report_json_path=resolved_paths.report_json_path,
                report_parquet_path=resolved_paths.report_parquet_path,
                candidates_json_path=resolved_paths.candidates_json_path,
                candidates_parquet_path=resolved_paths.candidates_parquet_path,
                equity_parquet_path=resolved_paths.equity_parquet_path,
                orders_parquet_path=resolved_paths.orders_parquet_path,
                trades_parquet_path=resolved_paths.trades_parquet_path,
                rejections_parquet_path=resolved_paths.rejections_parquet_path,
                manifest_path=resolved_paths.manifest_path,
            )
            session.add(row)
            session.commit()

    def update(self, item: BacktestListItem) -> None:
        with self._session_factory() as session:
            row = session.get(BacktestJob, item.id)
            if row is None:
                raise KeyError(f"Backtest job '{item.id}' not found")
            _apply_list_item(row, item)
            session.commit()

    def update_paths(self, backtest_id: str, paths: BacktestArtifactPaths) -> None:
        with self._session_factory() as session:
            row = session.get(BacktestJob, backtest_id)
            if row is None:
                raise KeyError(f"Backtest job '{backtest_id}' not found")
            row.config_path = paths.config_path or row.config_path
            row.report_json_path = paths.report_json_path or row.report_json_path
            row.report_parquet_path = paths.report_parquet_path or row.report_parquet_path
            row.candidates_json_path = paths.candidates_json_path or row.candidates_json_path
            row.candidates_parquet_path = paths.candidates_parquet_path or row.candidates_parquet_path
            row.equity_parquet_path = paths.equity_parquet_path or row.equity_parquet_path
            row.orders_parquet_path = paths.orders_parquet_path or row.orders_parquet_path
            row.trades_parquet_path = paths.trades_parquet_path or row.trades_parquet_path
            row.rejections_parquet_path = paths.rejections_parquet_path or row.rejections_parquet_path
            row.manifest_path = paths.manifest_path or row.manifest_path
            session.commit()

    def get(self, backtest_id: str) -> BacktestListItem | None:
        with self._session_factory() as session:
            row = session.get(BacktestJob, backtest_id)
            if row is None:
                return None
            return _row_to_list_item(row)

    def get_paths(self, backtest_id: str) -> BacktestArtifactPaths | None:
        with self._session_factory() as session:
            row = session.get(BacktestJob, backtest_id)
            if row is None:
                return None
            return _paths_from_row(row)

    def list_recent(self) -> list[BacktestListItem]:
        with self._session_factory() as session:
            rows = session.scalars(select(BacktestJob).order_by(BacktestJob.created_at.desc())).all()
            return [_row_to_list_item(row) for row in rows]

    def count(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(BacktestJob)) or 0)

    def list_recent_page(self, *, offset: int, limit: int) -> list[BacktestListItem]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(BacktestJob)
                .order_by(BacktestJob.created_at.desc())
                .offset(offset)
                .limit(limit)
            ).all()
            return [_row_to_list_item(row) for row in rows]

    def delete(self, backtest_id: str) -> bool:
        with self._session_factory() as session:
            row = session.get(BacktestJob, backtest_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
