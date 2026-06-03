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


class RiskModelService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        backtest_repo: SqlAlchemyBacktestJobRepository,
        risk_repo: SqlAlchemyRiskModelRepository,
        argo_submitter: ArgoWorkflowSubmitter | None = None,
    ):
        self._session_factory = session_factory
        self._backtest_repo = backtest_repo
        self._risk_repo = risk_repo
        self._argo_submitter = argo_submitter or ArgoWorkflowSubmitter()
        self._logger = logging.getLogger(__name__)

    def _artifact_dir_for_group(self, group_id: str) -> str:
        base = workflow_results_mount().rstrip("/")
        return f"{base}/risk-models/{group_id}"

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
            raise RiskModelValidationError("Provide at least one backtest_id")
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
                "Skipping local risk model artifact writes due to BACKTEST_RISK_SKIP_LOCAL_ARTIFACT_WRITES=1; "
                "artifact_dir=%s",
                artifact_dir,
            )
        elif not self._is_writable_dir(artifact_dir_path):
            self._logger.warning(
                "Risk model artifact_dir is not writable; skipping local writes (params.json will not be written). "
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
        rm_submitter = RiskModelArgoSubmitter(self._argo_submitter)
        wf_name, wf_ns = rm_submitter.submit(
            group_id=group_id,
            backtest_ids=request.backtest_ids,
            dataset_config=request.dataset_config,
            train_config=request.train_config,
            artifact_dir=artifact_dir,
        )
        self._risk_repo.update_group_workflow(group_id, argo_namespace=wf_ns, argo_workflow_name=wf_name)
        return CreateRiskModelResult(
            group_id=group_id,
            status="running",
            argo_namespace=wf_ns,
            argo_workflow_name=wf_name,
            artifact_dir=artifact_dir,
        )

    def get_argo_phase(self, group_id: str) -> str | None:
        detail = self._risk_repo.get_detail(group_id)
        if detail is None:
            return None
        if not detail.argo_workflow_name:
            return None
        return self._argo_submitter.get_workflow_phase(detail.argo_workflow_name)

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
                    "Failed to terminate risk model workflow; continuing with deletion. group_id=%s",
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
            raise RuntimeError(f"Risk model artifact_dir is not deletable: {artifact_dir}") from exc
        except OSError as exc:
            raise RuntimeError(f"Failed to delete risk model artifact_dir: {artifact_dir}") from exc
        return True
