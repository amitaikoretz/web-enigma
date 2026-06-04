from __future__ import annotations

import json
import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy.orm import sessionmaker, Session

from app.backtests.argo import ArgoWorkflowSubmitter
from app.backtests.persistence import SqlAlchemyBacktestJobRepository
from app.backtests.argo_workflow import workflow_results_mount
from app.risk.models_api import RiskModelCreateRequest
from app.risk.workflow_errors import WorkflowErrorDetails, extract_workflow_error_details
from app.risk.persistence import SqlAlchemyRiskModelRepository
from app.risk.argo import RiskModelArgoSubmitter


def _utc_now() -> datetime:
    return datetime.now(UTC)


class RiskModelValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CreateRiskModelResult:
    group_id: str
    status: str
    argo_namespace: str | None
    argo_workflow_name: str | None
    artifact_dir: str


@dataclass(frozen=True)
class RiskModelWorkflowErrorResult:
    group_id: str
    argo_namespace: str | None
    argo_workflow_name: str | None
    argo_phase: str | None
    available: bool
    status_message: str | None
    failed_node_name: str | None
    failed_template_name: str | None
    error_exception: str | None
    error_code_location: str | None
    error_call_stack: list[str]
    error_traceback: str | None


class RiskModelService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        backtest_repo: SqlAlchemyBacktestJobRepository,
        risk_repo: SqlAlchemyRiskModelRepository,
        argo_submitter: ArgoWorkflowSubmitter | None = None,
        family: str = "risk",
        family_slug: str = "risk-models",
        family_label: str = "Risk model",
    ):
        self._session_factory = session_factory
        self._backtest_repo = backtest_repo
        self._risk_repo = risk_repo
        self._argo_submitter = argo_submitter or ArgoWorkflowSubmitter()
        self._family = family
        self._family_slug = family_slug
        self._family_label = family_label
        self._logger = logging.getLogger(__name__)

    def _artifact_dir_for_group(self, group_id: str) -> str:
        base = workflow_results_mount().rstrip("/")
        return f"{base}/{self._family_slug}/{group_id}"

    def _is_writable_dir(self, candidate: Path) -> bool:
        try:
            if candidate.exists():
                if not candidate.is_dir():
                    return False
                return os.access(candidate, os.W_OK | os.X_OK)
            probe = candidate
            while not probe.exists() and probe.parent != probe:
                probe = probe.parent
            if not probe.exists() or not probe.is_dir():
                return False
            return os.access(probe, os.W_OK | os.X_OK)
        except OSError:
            return False

    def _validate_backtests(self, backtest_ids: list[str]) -> dict[str, str | None]:
        if not backtest_ids:
            raise RiskModelValidationError(f"Provide at least one backtest_id for {self._family_label.lower()}")
        report_paths: dict[str, str | None] = {}
        for backtest_id in backtest_ids:
            item = self._backtest_repo.get(backtest_id)
            if item is None:
                raise RiskModelValidationError(f"Backtest '{backtest_id}' not found")
            paths = self._backtest_repo.get_paths(backtest_id)
            if paths is None:
                raise RiskModelValidationError(f"Backtest '{backtest_id}' has no artifact paths")
            # v1 expects features + labels to exist (produced by backtest auxiliary pipeline).
            if not paths.features_parquet_path or not paths.labels_parquet_path:
                raise RiskModelValidationError(
                    f"Backtest '{backtest_id}' is missing features/labels parquet paths; "
                    "run auxiliary generation first."
                )
            report_paths[backtest_id] = paths.report_json_path
        return report_paths

    def create_and_submit_argo(self, request: RiskModelCreateRequest) -> CreateRiskModelResult:
        report_paths = self._validate_backtests(request.backtest_ids)

        group_id = uuid.uuid4().hex
        artifact_dir = self._artifact_dir_for_group(group_id)
        artifact_dir_path = Path(artifact_dir)
        skip_local_writes = os.environ.get("BACKTEST_RISK_SKIP_LOCAL_ARTIFACT_WRITES", "").lower() in {
            "1",
            "true",
            "yes",
        }
        if skip_local_writes:
            self._logger.warning(
                "Skipping local model artifact writes due to BACKTEST_RISK_SKIP_LOCAL_ARTIFACT_WRITES=1; "
                "artifact_dir=%s",
                artifact_dir,
            )
        elif not self._is_writable_dir(artifact_dir_path):
            self._logger.warning(
                "Model artifact_dir is not writable; skipping local writes (params.json will not be written). "
                "artifact_dir=%s",
                artifact_dir,
            )
        else:
            artifact_dir_path.mkdir(parents=True, exist_ok=True)
            (artifact_dir_path / "params.json").write_text(request.model_dump_json(indent=2), encoding="utf-8")

        params: dict[str, Any] = {
            "requested_at": _utc_now().isoformat(),
            "backtest_ids": request.backtest_ids,
            "targets": [t.model_dump(mode="json") for t in request.targets],
            "dataset_config": request.dataset_config,
            "train_config": request.train_config,
        }

        self._risk_repo.create_group(
            group_id=group_id,
            status="running",
            params=params,
            artifact_dir=artifact_dir,
            backtest_ids=request.backtest_ids,
            source_report_paths=report_paths,
        )

        # Submit workflow
        rm_submitter = RiskModelArgoSubmitter(
            self._argo_submitter,
            workflow_prefix=self._family_slug.rstrip("s"),
            component_label=self._family_slug.rstrip("s"),
        )
        wf_name, wf_ns = rm_submitter.submit(
            group_id=group_id,
            backtest_ids=request.backtest_ids,
            dataset_config=request.dataset_config,
            train_config=request.train_config,
            artifact_dir=artifact_dir,
            family=self._family,
        )
        self._risk_repo.update_group_workflow(group_id, argo_namespace=wf_ns, argo_workflow_name=wf_name)
        return CreateRiskModelResult(
            group_id=group_id,
            status="running",
            argo_namespace=wf_ns,
            argo_workflow_name=wf_name,
            artifact_dir=artifact_dir,
        )

    def retry_group(self, group_id: str) -> CreateRiskModelResult:
        detail = self._risk_repo.get_detail(group_id)
        if detail is None:
            raise RiskModelValidationError(f"{self._family_label} '{group_id}' not found")

        params = detail.params or {}
        try:
            request = RiskModelCreateRequest.model_validate(
                {
                    "backtest_ids": params.get("backtest_ids", []),
                    "targets": params.get("targets", []),
                    "dataset_config": params.get("dataset_config", {}),
                    "train_config": params.get("train_config", {}),
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise RiskModelValidationError(
                f"{self._family_label} '{group_id}' does not contain a retryable request payload"
            ) from exc

        return self.create_and_submit_argo(request)

    def get_argo_phase(self, group_id: str) -> str | None:
        detail = self._risk_repo.get_detail(group_id)
        if detail is None:
            return None
        if not detail.argo_workflow_name:
            return None
        return self._argo_submitter.get_workflow_phase(detail.argo_workflow_name)

    def get_workflow_errors(self, group_id: str) -> RiskModelWorkflowErrorResult | None:
        detail = self._risk_repo.get_detail(group_id)
        if detail is None:
            return None

        workflow = None
        if detail.argo_workflow_name:
            try:
                workflow = self._argo_submitter.get_workflow(
                    detail.argo_workflow_name,
                    namespace=detail.argo_namespace or None,
                )
            except Exception:  # noqa: BLE001
                self._logger.exception(
                    "Failed to load model workflow for error details; falling back to unavailable state. "
                    "group_id=%s workflow=%s namespace=%s",
                    group_id,
                    detail.argo_workflow_name,
                    detail.argo_namespace,
                )
                workflow = None

        error_details: WorkflowErrorDetails = extract_workflow_error_details(workflow)
        return RiskModelWorkflowErrorResult(
            group_id=detail.group_id,
            argo_namespace=detail.argo_namespace,
            argo_workflow_name=detail.argo_workflow_name,
            argo_phase=error_details.argo_phase,
            available=error_details.available,
            status_message=error_details.status_message,
            failed_node_name=error_details.failed_node_name,
            failed_template_name=error_details.failed_template_name,
            error_exception=error_details.error_exception,
            error_code_location=error_details.error_code_location,
            error_call_stack=error_details.error_call_stack,
            error_traceback=error_details.error_traceback,
        )

    def delete_group(self, group_id: str) -> bool:
        detail = self._risk_repo.get_detail(group_id)
        if detail is None:
            return False

        if detail.status in {"pending", "running"} and detail.argo_workflow_name:
            try:
                self._argo_submitter.terminate_workflow(
                    detail.argo_workflow_name,
                    namespace=detail.argo_namespace or None,
                )
            except Exception:  # noqa: BLE001
                self._logger.exception(
                    "Failed to terminate model workflow; continuing with deletion. group_id=%s",
                    group_id,
                )

        deleted = self._risk_repo.delete_group(group_id)
        if deleted is None:
            return False

        artifact_dir = deleted.artifact_dir
        try:
            shutil.rmtree(artifact_dir)
        except FileNotFoundError:
            return True
        except PermissionError as exc:
            raise RuntimeError(f"Model artifact_dir is not deletable: {artifact_dir}") from exc
        except OSError as exc:
            raise RuntimeError(f"Failed to delete model artifact_dir: {artifact_dir}") from exc
        return True
