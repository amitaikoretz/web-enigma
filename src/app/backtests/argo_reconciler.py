from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.backtests.argo import ArgoWorkflowSubmitter, load_argo_workflow_config
from app.backtests.models import BacktestListItem
from app.backtests.service import BacktestResultRepository, _selection_from_report, _utc_now
from app.output.models import BacktestReport


def update_metadata_from_report(
    backtest_id: str,
    report: BacktestReport,
    *,
    output_dir: Path,
) -> None:
    repository = BacktestResultRepository(output_dir)
    metadata = repository.load_metadata(backtest_id)
    if metadata is None:
        metadata = BacktestListItem(
            id=backtest_id,
            created_at=_utc_now(),
            updated_at=_utc_now(),
            status="completed",
            execution_backend="argo",
            total_runs=report.total_runs,
            selection=_selection_from_report(report),
        )
    else:
        metadata = metadata.model_copy(deep=True)

    metadata.status = "completed" if report.status != "failure" else "failed"
    metadata.report_status = report.status
    metadata.completed_runs = report.total_runs
    metadata.successful_runs = report.successful_runs
    metadata.failed_runs = report.failed_runs
    metadata.error_message = None if report.failed_runs == 0 else f"{report.failed_runs} run(s) failed"
    metadata.updated_at = _utc_now()
    repository.write_metadata(metadata)


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


def reconcile_backtest_workflows(output_dir: Path, *, once: bool = True) -> int:
    del once
    repository = BacktestResultRepository(output_dir)
    repository.ensure_ready()
    submitter = ArgoWorkflowSubmitter(load_argo_workflow_config())
    if not submitter.is_configured:
        return 0

    reconciled = 0
    for item in repository.list_backtests():
        if item.execution_backend != "argo" or not item.workflow_name:
            continue
        if item.status in {"completed", "failed"} and item.report_status is not None:
            continue

        phase = submitter.get_workflow_phase(item.workflow_name)
        report_path = repository.report_path(item.id)
        report_exists = report_path.exists()
        mapped_status = _map_workflow_phase(phase, report_exists=report_exists)
        if mapped_status is None:
            continue

        current = item.model_copy(deep=True)
        changed = False

        if mapped_status == "completed" and report_exists:
            report = repository.load_report(item.id)
            if report is not None:
                current.status = "completed"
                current.report_status = report.status
                current.completed_runs = report.total_runs
                current.successful_runs = report.successful_runs
                current.failed_runs = report.failed_runs
                current.error_message = None if report.failed_runs == 0 else f"{report.failed_runs} run(s) failed"
                changed = True
        elif mapped_status == "failed":
            current.status = "failed"
            current.error_message = f"Argo workflow phase={phase}"
            changed = True
        elif mapped_status == "running" and current.status != "running":
            current.status = "running"
            changed = True

        if changed:
            current.updated_at = datetime.now(UTC)
            repository.write_metadata(current)
            reconciled += 1

    return reconciled
