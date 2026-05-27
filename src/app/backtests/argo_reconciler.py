from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.backtests.argo import ArgoWorkflowSubmitter, _phase_from_workflow_resource, load_argo_workflow_config
from app.backtests.models import BacktestListItem
from app.backtests.persistence import (
    BacktestArtifactPaths,
    SqlAlchemyBacktestJobRepository,
    report_json_is_readable,
)
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
    write_artifacts: bool = True,
    artifact_paths: BacktestArtifactPaths | None = None,
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
        write_artifacts=write_artifacts,
        artifact_paths=artifact_paths,
    )


def _report_exists(
    item: BacktestListItem,
    artifact_store: BacktestArtifactStore,
    job_repository: SqlAlchemyBacktestJobRepository,
) -> bool:
    paths = job_repository.get_paths(item.id)
    if report_json_is_readable(paths):
        return True
    return artifact_store.report_path(item.id).is_file()


def _load_report_for_item(
    item: BacktestListItem,
    artifact_store: BacktestArtifactStore,
    job_repository: SqlAlchemyBacktestJobRepository,
) -> BacktestReport | None:
    paths = job_repository.get_paths(item.id)
    if paths and paths.report_json_path:
        report = artifact_store.load_report(item.id, report_json_path=paths.report_json_path)
        if report is not None:
            return report
    return artifact_store.load_report(item.id)


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
    workflow: dict | None = None,
) -> tuple[BacktestListItem, bool]:
    if item.execution_backend != "argo" or not item.workflow_name:
        return item, False

    if item.status in {"completed", "failed"} and item.report_status is not None:
        return item, False

    resolved_workflow = workflow
    if resolved_workflow is None:
        resolved_workflow = submitter.get_workflow(item.workflow_name)
    phase = _phase_from_workflow_resource(resolved_workflow) if resolved_workflow else None
    report_exists = _report_exists(item, artifact_store, job_repository)
    mapped_status = _map_workflow_phase(phase, report_exists=report_exists)
    if mapped_status is None:
        return item, False

    current = item.model_copy(deep=True)
    changed = False

    if mapped_status == "completed" and report_exists:
        paths = job_repository.get_paths(item.id)
        report = _load_report_for_item(item, artifact_store, job_repository)
        if report is not None and item.report_status is None:
            current = finalize_job_from_report(
                backtest_id=item.id,
                report=report,
                artifact_store=artifact_store,
                job_repository=job_repository,
                metadata=current,
                write_artifacts=False,
                artifact_paths=paths,
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
    workflow: dict | None = None,
) -> BacktestListItem | None:
    metadata = job_repository.get(backtest_id)
    if metadata is None:
        return None
    if metadata.execution_backend != "argo" or not metadata.workflow_name:
        return metadata

    if (
        metadata.status in {"completed", "failed"}
        and metadata.report_status is not None
    ):
        return metadata

    resolved_submitter = submitter or ArgoWorkflowSubmitter(load_argo_workflow_config())
    if not resolved_submitter.is_configured:
        return metadata

    updated, _changed = _reconcile_item(
        metadata,
        artifact_store,
        job_repository,
        resolved_submitter,
        workflow=workflow,
    )
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
