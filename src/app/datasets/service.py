from __future__ import annotations

import uuid
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.backtests.argo import ArgoWorkflowSubmitter, load_argo_workflow_config
from app.backtests.argo_workflow import workflow_results_mount
from app.datasets.argo_workflow import build_dataset_workflow_spec
from app.datasets.models import (
    DatasetCreateRequest,
    DatasetCreateResponse,
    DatasetDetailResponse,
    DatasetListItem,
    DatasetListPageResponse,
    DatasetStatusResponse,
    DatasetWorkflowErrorResponse,
)
from app.datasets.persistence import SqlAlchemyDatasetRepository
from app.risk.workflow_errors import extract_workflow_error_details
from app.settings.service import PlatformSettingsService


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DatasetService:
    _WORKFLOW_OUTPUT_NAME_ALIASES = {
        "dataset-path": ("dataset-path", "dataset_path"),
        "manifest-path": ("manifest-path", "manifest_path"),
        "options-dataset-path": ("options-dataset-path", "options_dataset_path"),
        "options-manifest-path": ("options-manifest-path", "options_manifest_path"),
    }

    def __init__(
        self,
        repository: SqlAlchemyDatasetRepository,
        settings_service: PlatformSettingsService,
        *,
        argo_submitter: ArgoWorkflowSubmitter | None = None,
    ):
        self.repository = repository
        self.settings_service = settings_service
        self.argo = argo_submitter or ArgoWorkflowSubmitter(load_argo_workflow_config())
        self._logger = logging.getLogger(__name__)

    def _is_writable_dir(self, candidate: Path) -> bool:
        try:
            if candidate.exists():
                if not candidate.is_dir():
                    return False
                return os.access(candidate, os.W_OK | os.X_OK)
            parent = candidate.parent
            if not parent.exists() or not parent.is_dir():
                return False
            return os.access(parent, os.W_OK | os.X_OK)
        except OSError:
            return False

    def _resolve_dataset_storage_root(self, settings) -> Path:
        configured = Path(settings.backtest_defaults.dataset_storage_root).expanduser()
        if self._is_writable_dir(configured):
            return configured.resolve()

        fallback = self.settings_service.path.parent.parent.resolve()
        self._logger.warning(
            "Dataset storage root %s is not writable; falling back to %s",
            configured,
            fallback,
        )
        return fallback

    _PHASE_TO_STATUS = {
        "Pending": "pending",
        "Running": "running",
        "Succeeded": "completed",
        "Failed": "failed",
        "Error": "failed",
    }

    def submit(self, payload: DatasetCreateRequest) -> DatasetCreateResponse:
        if not self.argo.is_configured:
            raise RuntimeError("Argo workflows are not configured; set ARGO_SERVER_URL (and token if needed).")

        settings = self.settings_service.load()
        output_dir = self._resolve_dataset_storage_root(settings)
        output_dir.mkdir(parents=True, exist_ok=True)
        workflow_output_dir = Path(workflow_results_mount()).resolve()
        if workflow_output_dir != output_dir:
            self._log_shared_storage_warning(output_dir, workflow_output_dir)

        dataset_id = uuid.uuid4().hex
        created_at = _utc_now()
        item = DatasetListItem(
            id=dataset_id,
            name=payload.name,
            symbol=payload.symbol,
            provider=payload.provider,
            resolution=payload.resolution,
            start_date=payload.start_date,
            end_date=payload.end_date,
            created_at=created_at,
            updated_at=created_at,
            status="pending",
            params_json=payload.model_dump(mode="json"),
            output_dir=str(output_dir),
        )
        self.repository.create(item)
        try:
            workflow_name, namespace = self._submit_workflow(
                dataset_id=dataset_id,
                payload=payload,
                output_dir=workflow_output_dir / dataset_id,
            )
            self.repository.update(
                item.model_copy(
                    update={
                        "argo_namespace": namespace,
                        "argo_workflow_name": workflow_name,
                        "updated_at": _utc_now(),
                    }
                )
            )
        except Exception as exc:  # noqa: BLE001
            self.repository.update(item.model_copy(update={"status": "failed", "error_message": str(exc), "updated_at": _utc_now()}))
            raise

        return DatasetCreateResponse(
            dataset_id=dataset_id,
            status="pending",
            status_url=f"/datasets/{dataset_id}/status",
            detail_url=f"/datasets/{dataset_id}",
        )

    def retry_dataset(self, dataset_id: str) -> DatasetCreateResponse:
        item = self.repository.get(dataset_id)
        if item is None:
            raise FileNotFoundError(f"Dataset '{dataset_id}' not found")
        if item.status not in {"failed", "completed"}:
            raise RuntimeError(f"Dataset '{dataset_id}' is not in a retryable state")

        payload = DatasetCreateRequest.model_validate(item.params_json)
        return self.submit(payload)

    def _submit_workflow(self, *, dataset_id: str, payload: DatasetCreateRequest, output_dir: Path) -> tuple[str, str]:
        resource = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {
                "name": f"dataset-{dataset_id[:12]}-{uuid.uuid4().hex[:6]}",
                "namespace": self.argo.config.namespace,
                "labels": {
                    "dataset-id": dataset_id,
                    "app.kubernetes.io/component": "dataset",
                },
            },
            "spec": {
                **build_dataset_workflow_spec(
                    symbol=payload.symbol,
                    provider=payload.provider,
                    resolution=payload.resolution,
                    start_date=payload.start_date.isoformat(),
                    end_date=payload.end_date.isoformat(),
                    options_enabled=payload.options.enabled,
                    options_feed=payload.options.feed,
                    output_dir=str(output_dir),
                    options_enabled_flag="--options-enabled" if payload.options.enabled else "--no-options-enabled",
                ),
                "arguments": {
                    "parameters": [
                        {"name": "symbol", "value": payload.symbol},
                        {"name": "provider", "value": payload.provider},
                        {"name": "resolution", "value": payload.resolution},
                        {"name": "start-date", "value": payload.start_date.isoformat()},
                        {"name": "end-date", "value": payload.end_date.isoformat()},
                        {"name": "options-enabled", "value": "true" if payload.options.enabled else "false"},
                        {
                            "name": "options-enabled-flag",
                            "value": "--options-enabled" if payload.options.enabled else "--no-options-enabled",
                        },
                        {"name": "options-feed", "value": payload.options.feed},
                        {"name": "output-dir", "value": str(output_dir)},
                    ]
                },
            },
        }
        namespace = self.argo.config.namespace
        response = self.argo._http_request(
            "POST",
            f"/api/v1/workflows/{namespace}",
            endpoint_name="datasets.argo.submit",
            json={"namespace": namespace, "serverDryRun": False, "workflow": resource},
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to submit Argo workflow: {response.status_code} {response.text}")
        return resource["metadata"]["name"], namespace

    def list_datasets(self) -> DatasetListPageResponse:
        items = self.repository.list_recent(limit=500)
        for item in items:
            self._refresh_from_argo(item, write_back=True)
            self._hydrate_artifact_paths(item, write_back=True)
        items = self.repository.list_recent(limit=500)
        return DatasetListPageResponse(items=items, total=len(items), page=1, page_size=len(items) or 1)

    def get_detail(self, dataset_id: str) -> DatasetDetailResponse | None:
        item = self.repository.get(dataset_id)
        if item is None:
            return None
        self._refresh_from_argo(item, write_back=True)
        self._hydrate_artifact_paths(item, write_back=True)
        item = self.repository.get(dataset_id)
        if item is None:
            return None
        return DatasetDetailResponse(metadata=item, symbol_options=self._resolve_symbol_options(item))

    def get_status(self, dataset_id: str) -> DatasetStatusResponse | None:
        item = self.repository.get(dataset_id)
        if item is None:
            return None
        self._refresh_from_argo(item, write_back=True)
        self._hydrate_artifact_paths(item, write_back=True)
        item = self.repository.get(dataset_id)
        if item is None:
            return None
        phase = self.get_argo_phase(dataset_id)
        return DatasetStatusResponse(
            **item.model_dump(),
            is_terminal=item.status in {"completed", "failed"},
            argo_phase=phase,
            progress_pct=100.0 if item.status in {"completed", "failed"} else 0.0,
        )

    def get_workflow_errors(self, dataset_id: str) -> DatasetWorkflowErrorResponse | None:
        item = self.repository.get(dataset_id)
        if item is None:
            return None

        workflow = None
        if item.argo_workflow_name:
            try:
                workflow = self.argo.get_workflow(item.argo_workflow_name, namespace=item.argo_namespace or None)
            except Exception:  # noqa: BLE001
                self._logger.exception(
                    "Failed to load dataset workflow for error details; falling back to unavailable state. "
                    "dataset_id=%s workflow=%s namespace=%s",
                    dataset_id,
                    item.argo_workflow_name,
                    item.argo_namespace,
                )
                workflow = None

        error_details = extract_workflow_error_details(workflow)
        return DatasetWorkflowErrorResponse(
            dataset_id=item.id,
            argo_namespace=item.argo_namespace,
            argo_workflow_name=item.argo_workflow_name,
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

    def get_argo_phase(self, dataset_id: str) -> str | None:
        item = self.repository.get(dataset_id)
        if item is None or not item.argo_workflow_name:
            return None
        workflow = self.argo.get_workflow(item.argo_workflow_name, namespace=item.argo_namespace)
        if workflow is None:
            return None
        return self._workflow_phase(workflow)

    def _refresh_from_argo(self, item: DatasetListItem, *, write_back: bool = True) -> None:
        if not item.argo_workflow_name:
            return
        workflow = self.argo.get_workflow(item.argo_workflow_name, namespace=item.argo_namespace)
        if workflow is None:
            return
        phase = self._workflow_phase(workflow)
        new_status = self._PHASE_TO_STATUS.get(phase)
        dataset_parquet_path = self._workflow_output_parameter(workflow, "dataset-path")
        manifest_path = self._workflow_output_parameter(workflow, "manifest-path")
        options_dataset_path = self._workflow_output_parameter(workflow, "options-dataset-path")
        options_manifest_path = self._workflow_output_parameter(workflow, "options-manifest-path")
        if (
            new_status is None
            and dataset_parquet_path is None
            and manifest_path is None
            and options_dataset_path is None
            and options_manifest_path is None
        ):
            return

        should_update = False
        updates: dict[str, object] = {}
        if new_status is not None and new_status != item.status:
            updates["status"] = new_status
            updates["progress_pct"] = 100.0 if new_status in {"completed", "failed"} else 0.0
            should_update = True
        if dataset_parquet_path and dataset_parquet_path != item.dataset_parquet_path:
            updates["dataset_parquet_path"] = dataset_parquet_path
            should_update = True
        if manifest_path and manifest_path != item.manifest_path:
            updates["manifest_path"] = manifest_path
            should_update = True
        if options_dataset_path and options_dataset_path != item.options_parquet_path:
            updates["options_parquet_path"] = options_dataset_path
            should_update = True
        if options_manifest_path and options_manifest_path != item.options_manifest_path:
            updates["options_manifest_path"] = options_manifest_path
            should_update = True
        if not should_update:
            return
        updated = item.model_copy(update={**updates, "updated_at": _utc_now()})
        if write_back:
            self.repository.update(updated)

    def delete_dataset(self, dataset_id: str) -> bool:
        item = self.repository.get(dataset_id)
        if item is None:
            return False
        self.repository.delete_artifacts(item)
        deleted = self.repository.delete(dataset_id)
        return deleted is not None

    def get_dataset_parquet_path(self, dataset_id: str) -> Path | None:
        item = self.repository.get(dataset_id)
        if item is None:
            return None
        resolved = self._resolve_dataset_parquet_path(item)
        if resolved is not None:
            return resolved
        return None

    def get_dataset_manifest_path(self, dataset_id: str) -> Path | None:
        item = self.repository.get(dataset_id)
        if item is None:
            return None
        resolved = self._resolve_dataset_manifest_path(item)
        if resolved is not None:
            return resolved
        return None

    def _workflow_output_parameter(self, workflow: dict[str, object], name: str) -> str | None:
        status = workflow.get("status")
        if not isinstance(status, dict):
            return None
        outputs = status.get("outputs")
        if not isinstance(outputs, dict):
            return None
        parameters = outputs.get("parameters")
        if not isinstance(parameters, list):
            return None
        aliases = self._WORKFLOW_OUTPUT_NAME_ALIASES.get(name, (name,))
        for parameter in parameters:
            if not isinstance(parameter, dict):
                continue
            param_name = parameter.get("name")
            value = parameter.get("value")
            if param_name in aliases and isinstance(value, str) and value.strip():
                return value
        return None

    def _resolve_dataset_path(self, item: DatasetListItem, path: Path) -> Path:
        workflow_root = Path(workflow_results_mount()).resolve()
        host_root = Path(item.output_dir).resolve()
        try:
            relative = path.resolve().relative_to(workflow_root)
        except ValueError:
            return path
        return host_root / relative

    def _resolve_artifact_path(self, item: DatasetListItem, path_str: str | None, fallback_name: str) -> Path | None:
        candidate_paths: list[Path] = []
        if path_str:
            candidate_paths.append(self._resolve_dataset_path(item, Path(path_str)))
        if item.output_dir:
            dataset_dir = Path(item.output_dir).resolve() / item.id
            candidate_paths.append(dataset_dir / fallback_name)
        if item.output_dir:
            candidate_paths.append(Path(item.output_dir) / fallback_name)
        for path in candidate_paths:
            if path.is_file():
                return path
        return None

    def _resolve_dataset_parquet_path(self, item: DatasetListItem) -> Path | None:
        return self._resolve_artifact_path(item, item.dataset_parquet_path, f"{item.symbol}-{item.provider}-{item.resolution}.parquet")

    def _resolve_dataset_manifest_path(self, item: DatasetListItem) -> Path | None:
        manifest_name = f"{item.symbol}-{item.provider}-{item.resolution}.manifest.json"
        if item.dataset_parquet_path:
            parquet_path = self._resolve_dataset_path(item, Path(item.dataset_parquet_path))
            if parquet_path.is_file():
                sibling_manifest = parquet_path.with_suffix(".manifest.json")
                if sibling_manifest.is_file():
                    return sibling_manifest
        return self._resolve_artifact_path(item, item.manifest_path, manifest_name)

    def _hydrate_artifact_paths(self, item: DatasetListItem, *, write_back: bool = True) -> None:
        dataset_parquet_path = self._resolve_dataset_parquet_path(item)
        manifest_path = self._resolve_dataset_manifest_path(item)
        updates: dict[str, object] = {}
        if dataset_parquet_path is not None and str(dataset_parquet_path) != item.dataset_parquet_path:
            updates["dataset_parquet_path"] = str(dataset_parquet_path)
        if manifest_path is not None and str(manifest_path) != item.manifest_path:
            updates["manifest_path"] = str(manifest_path)
        if not updates:
            return
        updated = item.model_copy(update={**updates, "updated_at": _utc_now()})
        if write_back:
            self.repository.update(updated)

    def _log_shared_storage_warning(self, output_dir: Path, workflow_output_dir: Path) -> None:
        self._logger.warning(
            "Dataset workflow writes under %s while the API mirrors results under %s; "
            "ensure both paths point to the same shared volume for host access.",
            workflow_output_dir,
            output_dir,
        )

    def _workflow_phase(self, workflow: dict[str, object]) -> str | None:
        status = workflow.get("status")
        if not isinstance(status, dict):
            return None
        phase = status.get("phase")
        if not isinstance(phase, str):
            return None
        return phase

    def _resolve_symbol_options(self, item: DatasetListItem) -> list[str]:
        options: list[str] = []
        parquet_path = self._resolve_dataset_parquet_path(item)
        if parquet_path is not None and parquet_path.is_file():
            try:
                frame = pd.read_parquet(parquet_path, columns=["symbol"])
            except Exception:
                try:
                    frame = pd.read_parquet(parquet_path)
                except Exception:
                    frame = None
            if frame is not None and "symbol" in frame.columns:
                seen: set[str] = set()
                for value in frame["symbol"].dropna().astype(str):
                    symbol = value.strip().upper()
                    if symbol and symbol not in seen:
                        seen.add(symbol)
                        options.append(symbol)

        if options:
            return options

        fallback_symbol = item.symbol.strip().upper()
        return [fallback_symbol] if fallback_symbol else []
