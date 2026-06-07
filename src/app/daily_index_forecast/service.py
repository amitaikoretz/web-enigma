from __future__ import annotations

import logging
import os
import shutil
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.backtests.argo import ArgoWorkflowSubmitter
from app.backtests.argo_progress_status import _workflow_progress_pct
from app.backtests.argo_workflow import workflow_results_mount
from app.daily_index_forecast.models import DailyIndexForecastCreateRequest
from app.daily_index_forecast.persistence import DailyIndexModelDetail, SqlAlchemyDailyIndexForecastRepository
from app.daily_index_forecast.argo import DailyIndexForecastArgoSubmitter
from app.risk.workflow_errors import WorkflowErrorDetails, extract_workflow_error_details


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DailyIndexForecastValidationError(ValueError):
    pass


@dataclass(frozen=True)
class CreateDailyIndexForecastResult:
    group_id: str
    feature_run_id: str
    name: str | None
    status: str
    argo_namespace: str | None
    argo_workflow_name: str | None
    artifact_dir: str


@dataclass(frozen=True)
class DailyIndexForecastWorkflowErrorResult:
    group_id: str
    feature_run_id: str
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


class DailyIndexForecastService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        repo: SqlAlchemyDailyIndexForecastRepository,
        argo_submitter: ArgoWorkflowSubmitter | None = None,
        family: str = "daily_index_forecast",
        family_slug: str = "daily-index-forecast-models",
        family_label: str = "Daily Index Forecast",
    ):
        self._session_factory = session_factory
        self._repo = repo
        self._argo_submitter = argo_submitter or ArgoWorkflowSubmitter()
        self._family = family
        self._family_slug = family_slug
        self._family_label = family_label
        self._logger = logging.getLogger(__name__)

    def _artifact_dir_for_group(self, group_id: str) -> str:
        base = workflow_results_mount().rstrip("/")
        return f"{base}/{self._family_slug}/{group_id}"

    def _artifact_dir_for_feature_run(self, feature_run_id: str) -> str:
        base = workflow_results_mount().rstrip("/")
        return f"{base}/{self._family_slug}/feature-runs/{feature_run_id}"

    def _normalize_name(self, name: str | None) -> str | None:
        if name is None:
            return None
        normalized = name.strip()
        return normalized or None

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

    def create_and_submit_argo(self, request: DailyIndexForecastCreateRequest) -> CreateDailyIndexForecastResult:
        group_id = uuid.uuid4().hex
        feature_run_id = uuid.uuid4().hex
        name = self._normalize_name(request.name)
        group_artifact_dir = self._artifact_dir_for_group(group_id)
        feature_artifact_dir = self._artifact_dir_for_feature_run(feature_run_id)

        group_artifact_dir_path = Path(group_artifact_dir)
        feature_artifact_dir_path = Path(feature_artifact_dir)
        skip_local_writes = os.environ.get("BACKTEST_DAILY_INDEX_SKIP_LOCAL_ARTIFACT_WRITES", "").lower() in {
            "1",
            "true",
            "yes",
        }
        if not skip_local_writes:
            if self._is_writable_dir(group_artifact_dir_path):
                group_artifact_dir_path.mkdir(parents=True, exist_ok=True)
                (group_artifact_dir_path / "params.json").write_text(request.model_dump_json(indent=2), encoding="utf-8")
            if self._is_writable_dir(feature_artifact_dir_path):
                feature_artifact_dir_path.mkdir(parents=True, exist_ok=True)
                (feature_artifact_dir_path / "params.json").write_text(
                    request.model_dump_json(indent=2),
                    encoding="utf-8",
                )

        group_params = {
            "requested_at": _utc_now().isoformat(),
            "name": name,
            "feature_run_id": feature_run_id,
            "universe": request.universe.model_dump(mode="json"),
            "feature_config": request.feature_config.model_dump(mode="json"),
            "walk_forward": request.walk_forward.model_dump(mode="json"),
            "train_config": request.train_config.model_dump(mode="json"),
            "costs": request.costs.model_dump(mode="json"),
            "data_cache": request.data_cache.model_dump(mode="json"),
        }
        feature_run_params = {
            "requested_at": _utc_now().isoformat(),
            "universe": request.universe.model_dump(mode="json"),
            "feature_config": request.feature_config.model_dump(mode="json"),
            "costs": request.costs.model_dump(mode="json"),
        }

        universe_symbol = request.universe.symbols[0].symbol
        benchmark_symbol = request.universe.benchmark.symbol if request.universe.benchmark is not None else None
        self._repo.create_feature_run(
            feature_run_id=feature_run_id,
            symbol=universe_symbol,
            benchmark_symbol=benchmark_symbol,
            decision_times=list(request.universe.decision_times),
            start_date=request.universe.start_date,
            end_date=request.universe.end_date,
            status="running",
            params=feature_run_params,
            artifact_dir=feature_artifact_dir,
        )
        self._repo.create_group(
            group_id=group_id,
            feature_run_id=feature_run_id,
            name=name,
            status="running",
            params=group_params,
            artifact_dir=group_artifact_dir,
        )

        submitter = DailyIndexForecastArgoSubmitter(self._argo_submitter)
        wf_name, wf_ns = submitter.submit(
            group_id=group_id,
            feature_run_id=feature_run_id,
            universe_json=request.universe.model_dump_json(),
            feature_config_json=request.feature_config.model_dump_json(),
            walk_forward_json=request.walk_forward.model_dump_json(),
            train_config_json=request.train_config.model_dump_json(),
            costs_json=request.costs.model_dump_json(),
            data_cache_json=request.data_cache.model_dump_json(),
            artifact_dir=group_artifact_dir,
            feature_artifact_dir=feature_artifact_dir,
            family=self._family,
        )
        self._repo.update_group_workflow(group_id, argo_namespace=wf_ns, argo_workflow_name=wf_name)
        self._repo.update_feature_run_workflow(feature_run_id, argo_namespace=wf_ns, argo_workflow_name=wf_name)
        return CreateDailyIndexForecastResult(
            group_id=group_id,
            feature_run_id=feature_run_id,
            name=name,
            status="running",
            argo_namespace=wf_ns,
            argo_workflow_name=wf_name,
            artifact_dir=group_artifact_dir,
        )

    def retry_group(self, group_id: str) -> CreateDailyIndexForecastResult:
        detail = self._repo.get_detail(group_id)
        if detail is None:
            raise DailyIndexForecastValidationError(f"{self._family_label} '{group_id}' not found")
        params = detail.params or {}
        try:
            request = DailyIndexForecastCreateRequest.model_validate(
                {
                    "name": params.get("name", detail.name),
                    "universe": params["universe"],
                    "feature_config": params.get("feature_config", {}),
                    "walk_forward": params.get("walk_forward", {}),
                    "train_config": params.get("train_config", {}),
                    "costs": params.get("costs", {}),
                    "data_cache": params.get("data_cache", {}),
                }
            )
        except Exception as exc:  # noqa: BLE001
            raise DailyIndexForecastValidationError(
                f"{self._family_label} '{group_id}' does not contain a retryable request payload"
            ) from exc
        return self.create_and_submit_argo(request)

    def update_group_name(self, group_id: str, name: str | None):
        normalized_name = self._normalize_name(name)
        updated = self._repo.update_group_name(group_id, normalized_name)
        if updated is None:
            raise DailyIndexForecastValidationError(f"{self._family_label} '{group_id}' not found")
        return updated

    def get_argo_phase(self, group_id: str) -> str | None:
        detail = self._repo.get_detail(group_id)
        if detail is None or not detail.argo_workflow_name:
            return None
        return self._argo_submitter.get_workflow_phase(detail.argo_workflow_name, namespace=detail.argo_namespace)

    def get_argo_progress_pct(self, group_id: str) -> float | None:
        detail = self._repo.get_detail(group_id)
        if detail is None or not detail.argo_workflow_name:
            return None
        try:
            workflow = self._argo_submitter.get_workflow(detail.argo_workflow_name, namespace=detail.argo_namespace)
        except Exception:  # noqa: BLE001
            self._logger.exception(
                "Failed to load daily index forecast workflow progress; falling back to no progress. "
                "group_id=%s workflow=%s namespace=%s",
                group_id,
                detail.argo_workflow_name,
                detail.argo_namespace,
            )
            return None
        return _workflow_progress_pct(workflow)

    def get_workflow_errors(self, group_id: str) -> DailyIndexForecastWorkflowErrorResult | None:
        detail = self._repo.get_detail(group_id)
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
                    "Failed to load daily index forecast workflow for error details; falling back to unavailable state. "
                    "group_id=%s workflow=%s namespace=%s",
                    group_id,
                    detail.argo_workflow_name,
                    detail.argo_namespace,
                )
                workflow = None

        error_details: WorkflowErrorDetails = extract_workflow_error_details(workflow)
        return DailyIndexForecastWorkflowErrorResult(
            group_id=detail.group_id,
            feature_run_id=detail.feature_run_id,
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
        detail = self._repo.get_detail(group_id)
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
                    "Failed to terminate daily index forecast workflow; continuing with deletion. group_id=%s",
                    group_id,
                )

        deleted = self._repo.delete_group(group_id)
        if deleted is None:
            return False

        artifact_dirs = [deleted.artifact_dir]
        if deleted.feature_run_artifact_dir:
            artifact_dirs.append(deleted.feature_run_artifact_dir)
        for artifact_dir in artifact_dirs:
            try:
                shutil.rmtree(artifact_dir)
            except FileNotFoundError:
                continue
            except PermissionError as exc:
                raise RuntimeError(f"Daily index forecast artifact_dir is not deletable: {artifact_dir}") from exc
            except OSError as exc:
                raise RuntimeError(f"Failed to delete daily index forecast artifact_dir: {artifact_dir}") from exc
        return True
