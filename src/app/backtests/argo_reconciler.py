from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.backtests.argo import ArgoWorkflowSubmitter, load_argo_workflow_config
from app.backtests.models import BacktestListItem
from app.backtests.persistence import SqlAlchemyBacktestJobRepository
from app.backtests.service import (
    BacktestArtifactStore,
    _mark_running,
    _mark_terminal,
    finalize_job_from_report,
)
from app.db.session import get_session_factory
from app.output.models import BacktestReport


def update_metadata_from_report(
    backtest_id: str,
    report: BacktestReport,
    *,
    output_dir: Path,
    session_factory: sessionmaker[Session] | None = None,
) -> None:
    resolved_factory = session_factory or get_session_factory()
    artifact_store = BacktestArtifactStore(output_dir)
    job_repository = SqlAlchemyBacktestJobRepository(resolved_factory)
    metadata = job_repository.get(backtest_id)
    finalize_job_from_report(
        backtest_id=backtest_id,
        report=report,
        artifact_store=artifact_store,
        job_repository=job_repository,
        metadata=metadata,
    )


def _map_workflow_phase(phase: str | None, *, report_exists: bool) -> str | None:
    if phase is None:
        return None
    normalized = phase.lower()
    if normalized == "succeeded":
        return "completed" if report_exists else "running"
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"running", "pending"}:
        return "running"
    return "running"


def _reconcile_item(
    item: BacktestListItem,
    artifact_store: BacktestArtifactStore,
    job_repository: SqlAlchemyBacktestJobRepository,
    submitter: ArgoWorkflowSubmitter,
) -> tuple[BacktestListItem, bool]:
    if item.execution_backend != "argo" or not item.workflow_name:
        return item, False
    if item.status in {"completed", "failed"} and item.report_status is not None:
        return item, False

    phase = submitter.get_workflow_phase(item.workflow_name)
    report_path = artifact_store.report_path(item.id)
    report_exists = report_path.exists()
    mapped_status = _map_workflow_phase(phase, report_exists=report_exists)
    if mapped_status is None:
        return item, False

    current = item.model_copy(deep=True)
    changed = False

    if mapped_status == "completed" and report_exists:
        report = artifact_store.load_report(item.id)
        if report is not None:
            current = finalize_job_from_report(
                backtest_id=item.id,
                report=report,
                artifact_store=artifact_store,
                job_repository=job_repository,
                metadata=current,
            )
            changed = True
    elif mapped_status == "failed":
        current = _mark_terminal(current, status="failed")
        current.error_message = f"Argo workflow phase={phase}"
        changed = True
    elif mapped_status == "running" and current.status != "running":
        current = _mark_running(current)
        changed = True

    if changed and mapped_status != "completed":
        current.updated_at = datetime.now(UTC)
        job_repository.update(current)
    return current, changed


def reconcile_backtest(
    backtest_id: str,
    artifact_store: BacktestArtifactStore,
    job_repository: SqlAlchemyBacktestJobRepository,
    submitter: ArgoWorkflowSubmitter | None = None,
) -> BacktestListItem | None:
    metadata = job_repository.get(backtest_id)
    if metadata is None:
        return None
    if metadata.execution_backend != "argo" or not metadata.workflow_name:
        return metadata
    if metadata.status in {"completed", "failed"} and metadata.report_status is not None:
        return metadata

    resolved_submitter = submitter or ArgoWorkflowSubmitter(load_argo_workflow_config())
    if not resolved_submitter.is_configured:
        return metadata

    updated, _changed = _reconcile_item(metadata, artifact_store, job_repository, resolved_submitter)
    return updated


def reconcile_backtest_workflows(
    output_dir: Path,
    *,
    once: bool = True,
    session_factory: sessionmaker[Session] | None = None,
) -> int:
    del once
    resolved_factory = session_factory or get_session_factory()
    artifact_store = BacktestArtifactStore(output_dir)
    job_repository = SqlAlchemyBacktestJobRepository(resolved_factory)
    submitter = ArgoWorkflowSubmitter(load_argo_workflow_config())
    if not submitter.is_configured:
        return 0

    reconciled = 0
    for item in job_repository.list_recent():
        if item.execution_backend != "argo":
            continue
        _updated, changed = _reconcile_item(item, artifact_store, job_repository, submitter)
        if changed:
            reconciled += 1

    return reconciled
