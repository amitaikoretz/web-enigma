from __future__ import annotations

import json
import uuid
import logging
import os
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from app.backtests.argo import ArgoWorkflowSubmitter, load_argo_workflow_config
from app.backtests.argo_workflow import workflow_results_mount
from app.datasets.argo_workflow import build_dataset_workflow_spec
from app.datasets.argo_progress_status import compute_dataset_progress_pct
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


def _dataset_output_subdir(dataset_id: str, created_at: datetime) -> str:
    return f"{created_at.date().isoformat()}/{dataset_id}"


def _normalize_symbols(symbols: list[str], fallback_symbol: str | None = None) -> list[str]:
    normalized: list[str] = []
    for value in symbols:
        symbol = value.strip().upper()
        if symbol and symbol not in normalized:
            normalized.append(symbol)
    if not normalized and fallback_symbol:
        fallback = fallback_symbol.strip().upper()
        if fallback:
            normalized.append(fallback)
    return normalized


def _artifact_slug(item: DatasetListItem) -> str:
    symbols = item.symbols or ([item.symbol] if item.symbol.strip() else [])
    normalized = _normalize_symbols(symbols, item.symbol)
    return "-".join(normalized) if normalized else (item.symbol.strip().upper() or item.id)


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
        symbols = _normalize_symbols(payload.symbols, payload.symbol)
        primary_symbol = symbols[0]
        item = DatasetListItem(
            id=dataset_id,
            name=payload.name,
            symbol=primary_symbol,
            symbols=symbols,
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
            workflow_output_dir = workflow_output_dir / _dataset_output_subdir(dataset_id, created_at)
            workflow_name, namespace = self._submit_workflow(
                dataset_id=dataset_id,
                payload=payload,
                symbols=symbols,
                output_dir=workflow_output_dir,
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

    def _submit_workflow(
        self,
        *,
        dataset_id: str,
        payload: DatasetCreateRequest,
        symbols: list[str],
        output_dir: Path,
    ) -> tuple[str, str]:
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
                    symbols=symbols,
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
                        {"name": "symbols", "value": ",".join(symbols)},
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
        payload = item.model_dump()
        payload["progress_pct"] = item.progress_pct
        return DatasetStatusResponse(
            **payload,
            is_terminal=item.status in {"completed", "failed"},
            argo_phase=phase,
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
        progress_pct = compute_dataset_progress_pct(item, workflow)
        if (
            new_status is None
            and dataset_parquet_path is None
            and manifest_path is None
            and options_dataset_path is None
            and options_manifest_path is None
            and progress_pct is None
        ):
            return

        should_update = False
        updates: dict[str, object] = {}
        if new_status is not None and new_status != item.status:
            updates["status"] = new_status
            updates["progress_pct"] = 100.0 if new_status in {"completed", "failed"} else 0.0
            should_update = True
        elif progress_pct is not None:
            clamped = max(item.progress_pct, min(progress_pct, 99.0))
            if clamped > item.progress_pct:
                updates["progress_pct"] = clamped
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
        deleted_artifacts = self.repository.delete_artifacts(item)
        deleted = self.repository.delete(dataset_id)
        return deleted is not None or deleted_artifacts

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

    def _artifact_root_candidates(self, item: DatasetListItem) -> list[Path]:
        roots: list[Path] = []
        settings_path = getattr(self.settings_service, "path", None)
        candidates = [
            Path(item.output_dir),
            Path(workflow_results_mount()),
            Path.cwd() / "data" / "backtest-results",
        ]
        if settings_path is not None:
            candidates.append(Path(settings_path).parent.parent)
        for candidate in candidates:
            try:
                resolved = candidate.expanduser().resolve()
            except OSError:
                continue
            if resolved not in roots:
                roots.append(resolved)
        return roots

    def _artifact_directories(self, item: DatasetListItem, root: Path) -> list[Path]:
        dated_dir = root / item.created_at.date().isoformat() / item.id
        legacy_dir = root / item.id
        return [dated_dir, legacy_dir] if dated_dir != legacy_dir else [legacy_dir]

    def _translate_from_workflow_mount(self, item: DatasetListItem, path: Path, *, host_root: Path) -> Path:
        workflow_root = Path(workflow_results_mount()).resolve()
        try:
            relative = path.resolve().relative_to(workflow_root)
        except ValueError:
            return path
        return host_root / relative

    def _load_manifest_payload(self, path: Path) -> dict[str, object] | None:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

    def _is_matching_artifact_manifest(self, item: DatasetListItem, path: Path, *, dataset_kind: str) -> bool:
        payload = self._load_manifest_payload(path)
        if not isinstance(payload, dict):
            return False
        if payload.get("dataset_id") != item.id:
            return False
        if payload.get("dataset_kind") != dataset_kind:
            return False
        return True

    def _resolve_manifest_path_from_roots(
        self,
        item: DatasetListItem,
        *,
        dataset_kind: str,
        preferred_path: Path | None,
        fallback_name: str,
    ) -> Path | None:
        if dataset_kind == "market":
            candidate_names = [
                fallback_name,
                f"{_artifact_slug(item)}-{item.provider}-{item.resolution}.manifest.json",
                "manifest.json",
                "market.manifest.json",
            ]
        else:
            candidate_names = [
                fallback_name,
                f"{_artifact_slug(item)}-alpaca-options-{item.resolution}.manifest.json",
                "manifest.json",
                "options.manifest.json",
            ]
        seen_paths: set[Path] = set()
        roots = self._artifact_root_candidates(item)
        for root in roots:
            for artifact_dir in self._artifact_directories(item, root):
                candidate_paths: list[Path] = []
                if preferred_path is not None:
                    candidate_paths.append(self._translate_from_workflow_mount(item, preferred_path, host_root=root))
                candidate_paths.append(artifact_dir / fallback_name)
                candidate_paths.append(artifact_dir / "manifest.json")
                for name in candidate_names:
                    candidate_paths.append(artifact_dir / name)
                for candidate in artifact_dir.glob("*.manifest.json"):
                    candidate_paths.append(candidate)

                for candidate in candidate_paths:
                    if candidate in seen_paths:
                        continue
                    seen_paths.add(candidate)
                    if candidate.is_file():
                        if candidate.name in candidate_names or candidate.name == "manifest.json":
                            return candidate
                        if self._is_matching_artifact_manifest(item, candidate, dataset_kind=dataset_kind):
                            return candidate
        return None

    def _resolve_dataset_artifact_from_roots(
        self,
        item: DatasetListItem,
        *,
        dataset_kind: str,
        stored_path: str | None,
        fallback_name: str,
        preferred_manifest_path: str | None = None,
    ) -> tuple[Path | None, Path | None]:
        roots = self._artifact_root_candidates(item)
        candidate_paths: list[Path] = []
        if stored_path:
            candidate_paths.append(Path(stored_path))
        for root in roots:
            for artifact_dir in self._artifact_directories(item, root):
                candidate_paths.append(artifact_dir / fallback_name)
                candidate_paths.append(artifact_dir / "dataset.parquet" if dataset_kind == "market" else artifact_dir / "options.parquet")
                if stored_path:
                    candidate_paths.append(self._translate_from_workflow_mount(item, Path(stored_path), host_root=root))

        for candidate in candidate_paths:
            if candidate.is_file():
                manifest_path = candidate.with_suffix(".manifest.json")
                if manifest_path.is_file() and self._is_matching_artifact_manifest(item, manifest_path, dataset_kind=dataset_kind):
                    return candidate, manifest_path
                found_manifest = self._resolve_manifest_path_from_roots(
                    item,
                    dataset_kind=dataset_kind,
                    preferred_path=Path(preferred_manifest_path) if preferred_manifest_path else None,
                    fallback_name=manifest_path.name,
                )
                return candidate, found_manifest

        manifest_path = None
        if stored_path:
            manifest_path = Path(stored_path).with_suffix(".manifest.json")
            if not manifest_path.is_file():
                manifest_path = None
        found_manifest = self._resolve_manifest_path_from_roots(
            item,
            dataset_kind=dataset_kind,
            preferred_path=Path(preferred_manifest_path) if preferred_manifest_path else manifest_path,
            fallback_name=fallback_name.replace(".parquet", ".manifest.json"),
        )
        if found_manifest is None:
            return None, None

        manifest_payload = self._load_manifest_payload(found_manifest)
        output_path = None
        if isinstance(manifest_payload, dict):
            raw_output_path = manifest_payload.get("output_path")
            if isinstance(raw_output_path, str) and raw_output_path.strip():
                translated = self._translate_from_workflow_mount(item, Path(raw_output_path), host_root=found_manifest.parent.parent)
                output_path = translated if translated.is_file() else Path(raw_output_path)
        if output_path is not None and output_path.is_file():
            return output_path, found_manifest
        return None, found_manifest

    def _resolve_artifact_path(self, item: DatasetListItem, path_str: str | None, fallback_name: str) -> Path | None:
        candidate_paths: list[Path] = []
        if path_str:
            candidate_paths.append(self._resolve_dataset_path(item, Path(path_str)))
        if item.output_dir:
            dataset_root = Path(item.output_dir).resolve()
            for dataset_dir in self._artifact_directories(item, dataset_root):
                candidate_paths.append(dataset_dir / fallback_name)
        if item.output_dir:
            candidate_paths.append(Path(item.output_dir) / fallback_name)
        for path in candidate_paths:
            if path.is_file():
                return path
        return None

    def _resolve_dataset_parquet_path(self, item: DatasetListItem) -> Path | None:
        resolved, _manifest = self._resolve_dataset_artifact_from_roots(
            item,
            dataset_kind="market",
            stored_path=item.dataset_parquet_path,
            fallback_name=f"{_artifact_slug(item)}-{item.provider}-{item.resolution}.parquet",
            preferred_manifest_path=item.manifest_path,
        )
        return resolved

    def _resolve_dataset_manifest_path(self, item: DatasetListItem) -> Path | None:
        _parquet_path, manifest_path = self._resolve_dataset_artifact_from_roots(
            item,
            dataset_kind="market",
            stored_path=item.dataset_parquet_path,
            fallback_name=f"{_artifact_slug(item)}-{item.provider}-{item.resolution}.parquet",
            preferred_manifest_path=item.manifest_path,
        )
        return manifest_path

    def _resolve_options_dataset_parquet_path(self, item: DatasetListItem) -> Path | None:
        if not item.options_manifest_path and not item.options_parquet_path:
            return None
        resolved, _manifest = self._resolve_dataset_artifact_from_roots(
            item,
            dataset_kind="options",
            stored_path=item.options_parquet_path,
            fallback_name=f"{_artifact_slug(item)}-alpaca-options-{item.resolution}.parquet",
            preferred_manifest_path=item.options_manifest_path,
        )
        return resolved

    def _resolve_options_dataset_manifest_path(self, item: DatasetListItem) -> Path | None:
        if not item.options_manifest_path and not item.options_parquet_path:
            return None
        _parquet_path, manifest_path = self._resolve_dataset_artifact_from_roots(
            item,
            dataset_kind="options",
            stored_path=item.options_parquet_path,
            fallback_name=f"{_artifact_slug(item)}-alpaca-options-{item.resolution}.parquet",
            preferred_manifest_path=item.options_manifest_path,
        )
        return manifest_path

    def _hydrate_artifact_paths(self, item: DatasetListItem, *, write_back: bool = True) -> None:
        dataset_parquet_path = self._resolve_dataset_parquet_path(item)
        manifest_path = self._resolve_dataset_manifest_path(item)
        options_dataset_path = self._resolve_options_dataset_parquet_path(item)
        options_manifest_path = self._resolve_options_dataset_manifest_path(item)
        updates: dict[str, object] = {}
        if dataset_parquet_path is not None and str(dataset_parquet_path) != item.dataset_parquet_path:
            updates["dataset_parquet_path"] = str(dataset_parquet_path)
        if manifest_path is not None and str(manifest_path) != item.manifest_path:
            updates["manifest_path"] = str(manifest_path)
        if options_dataset_path is not None and str(options_dataset_path) != item.options_parquet_path:
            updates["options_parquet_path"] = str(options_dataset_path)
        if options_manifest_path is not None and str(options_manifest_path) != item.options_manifest_path:
            updates["options_manifest_path"] = str(options_manifest_path)
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
