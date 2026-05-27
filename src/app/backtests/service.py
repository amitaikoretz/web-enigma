from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from sqlalchemy.orm import Session, sessionmaker

from app.backtests.argo import ArgoWorkflowSubmitter
from app.backtests.argo_workflow import workflow_artifact_paths, workflow_results_mount
from app.backtests.artifacts import (
    backtest_artifact_dir,
    default_artifact_paths,
    hydrate_report_from_artifacts,
    inventory_backtest_artifacts,
    summarize_backtest_artifacts,
    write_report_artifacts,
)
from app.backtests.models import (
    ArgoSplitBy,
    BacktestArgoLaunchRequest,
    BacktestArgoLaunchResponse,
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestListPageResponse,
    BacktestSelectionSummary,
    BacktestStatusResponse,
)
from app.backtests.persistence import (
    BacktestArtifactPaths,
    SqlAlchemyBacktestJobRepository,
    report_json_is_readable,
)
from app.backtests.sharding import resolve_split_by
from app.config.models import (
    AnalyzerConfig,
    BacktestConfig,
    DataCacheConfig,
    BrokerConfig,
)
from app.engine.runner import RunExecutionOptions, run_backtests_with_hooks
from app.settings.models import PlatformSettings
from app.settings.service import PlatformSettingsService
from app.strategies.auditor_logging import configure_strategy_logging
from app.output import BacktestReport, write_backtest_report_json
from app.output.models import RunResult


class ArgoNotConfiguredError(RuntimeError):
    pass


class BacktestAlreadyExistsError(RuntimeError):
    pass


class ArgoResultsNotSharedError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _mark_running(item: BacktestListItem) -> BacktestListItem:
    current = item.model_copy(deep=True)
    now = _utc_now()
    current.status = "running"
    current.updated_at = now
    if current.started_at is None:
        current.started_at = now
    return current


def _mark_terminal(item: BacktestListItem, *, status: str) -> BacktestListItem:
    current = item.model_copy(deep=True)
    now = _utc_now()
    current.status = status  # type: ignore[assignment]
    current.updated_at = now
    if current.finished_at is None:
        current.finished_at = now
    return current


def config_to_yaml_text(config_raw: dict[str, Any]) -> str:
    return yaml.safe_dump(config_raw, default_flow_style=False, sort_keys=False)


def _build_selection_summary(payload: BacktestCreateRequest) -> BacktestSelectionSummary:
    return BacktestSelectionSummary(
        start_date=payload.start_date,
        end_date=payload.end_date,
        resolution=payload.resolution,
        feed=payload.feed,
        symbols=payload.symbols,
        strategies=[strategy.name for strategy in payload.strategies],
    )


def _selection_from_report(report: BacktestReport) -> BacktestSelectionSummary:
    input_config = report.input_config
    runs = input_config.get("runs", []) if isinstance(input_config, dict) else []
    symbols: list[str] = []
    strategies: list[str] = []
    start_date = None
    end_date = None
    resolution = "1d"
    feed = "iex"

    for run in runs:
        if not isinstance(run, dict):
            continue
        if start_date is None:
            start_date = run.get("start_date")
        end_date = run.get("end_date", end_date)
        data = run.get("data", {})
        if isinstance(data, dict):
            symbol = data.get("symbol")
            if isinstance(symbol, str) and symbol not in symbols:
                symbols.append(symbol)
            resolution = data.get("interval", resolution)
            feed = data.get("feed", feed)
        strategy = run.get("strategy")
        if isinstance(strategy, str) and strategy not in strategies:
            strategies.append(strategy)

    return BacktestSelectionSummary(
        start_date=start_date,
        end_date=end_date,
        resolution=resolution,
        feed=feed,
        symbols=symbols,
        strategies=strategies,
    )


def _selection_from_config_raw(config_raw: dict[str, Any]) -> BacktestSelectionSummary | None:
    runs = config_raw.get("runs")
    if not isinstance(runs, list) or not runs:
        return None
    symbols: list[str] = []
    strategies: list[str] = []
    start_date = None
    end_date = None
    resolution = "1d"
    feed = "iex"

    for run in runs:
        if not isinstance(run, dict):
            continue
        if start_date is None:
            start_date = run.get("start_date")
        end_date = run.get("end_date", end_date)
        data = run.get("data", {})
        if isinstance(data, dict):
            symbol = data.get("symbol")
            if isinstance(symbol, str) and symbol not in symbols:
                symbols.append(symbol)
            resolution = data.get("interval", resolution)
            feed = data.get("feed", feed)
        strategy = run.get("strategy")
        if isinstance(strategy, str) and strategy not in strategies:
            strategies.append(strategy)
        multi = run.get("strategies")
        if isinstance(multi, list):
            for entry in multi:
                if isinstance(entry, dict):
                    name = entry.get("name")
                    if isinstance(name, str) and name not in strategies:
                        strategies.append(name)

    if start_date is None or end_date is None:
        return None
    return BacktestSelectionSummary(
        start_date=start_date,
        end_date=end_date,
        resolution=resolution,
        feed=feed,  # type: ignore[arg-type]
        symbols=symbols or ["UNKNOWN"],
        strategies=strategies or ["unknown"],
    )


def _parse_inline_config(config_text: str, fmt: str) -> dict[str, Any]:
    if fmt == "json":
        data = json.loads(config_text)
    else:
        data = yaml.safe_load(config_text)
    if not isinstance(data, dict):
        raise ValueError("Config root must be an object")
    return data


def build_backtest_config_raw(payload: BacktestCreateRequest, backtest_id: str) -> dict[str, Any]:
    broker = payload.broker or BrokerConfig()
    analyzers = payload.analyzers or AnalyzerConfig(
        include_equity_curve=True,
        include_trade_log=True,
        include_order_log=True,
    )
    execution = payload.execution
    runs: list[dict[str, Any]] = []

    for strategy in payload.strategies:
        for symbol in payload.symbols:
            run_index = len(runs) + 1
            run_id = f"{backtest_id}:{run_index:03d}:{symbol}:{strategy.name}"
            run_payload: dict[str, Any] = {
                "run_id": run_id,
                "name": f"{symbol} {strategy.name}",
                "start_date": payload.start_date.isoformat(),
                "end_date": payload.end_date.isoformat(),
                "data": {
                    "type": "alpaca",
                    "symbol": symbol,
                    "interval": payload.resolution,
                    "feed": payload.feed,
                },
                "strategy": strategy.name,
                "strategy_params": strategy.params,
                "broker": broker.model_dump(mode="json"),
                "analyzers": analyzers.model_dump(mode="json"),
            }
            if execution is not None:
                run_payload["execution"] = execution.model_dump(mode="json")
            runs.append(run_payload)

    return {"runs": runs}


def build_backtest_config(payload: BacktestCreateRequest, backtest_id: str) -> BacktestConfig:
    return BacktestConfig.model_validate(build_backtest_config_raw(payload, backtest_id))


def _is_terminal_status(status: str) -> bool:
    return status in {"completed", "failed"}


def _progress_pct(completed_runs: int, total_runs: int, status: str) -> float:
    if total_runs == 0:
        return 0.0
    if status == "completed":
        return 100.0
    return min(100.0, (completed_runs / total_runs) * 100.0)


def compute_completed_runs(metadata: BacktestListItem, repository: BacktestArtifactStore) -> int:
    if metadata.status in {"completed", "failed"}:
        return metadata.completed_runs
    if metadata.execution_backend != "argo":
        return metadata.completed_runs

    manifest_path = repository.output_dir / metadata.id / "manifest.json"
    if not manifest_path.exists():
        return metadata.completed_runs

    from app.backtests.sharding import load_shard_manifest

    plan = load_shard_manifest(manifest_path)
    completed = 0
    for shard in plan.shards:
        shard_path = Path(shard.output_path)
        if not shard_path.exists():
            continue
        try:
            shard_report = BacktestReport.model_validate_json(shard_path.read_text(encoding="utf-8"))
            completed += shard_report.total_runs
        except (ValueError, OSError):
            continue
    return min(completed, metadata.total_runs)


def build_status_response(metadata: BacktestListItem, completed_runs: int) -> BacktestStatusResponse:
    progress = _progress_pct(completed_runs, metadata.total_runs, metadata.status)
    payload = metadata.model_dump()
    payload["completed_runs"] = completed_runs
    payload["progress_pct"] = progress
    payload["is_terminal"] = _is_terminal_status(metadata.status)
    return BacktestStatusResponse(**payload)


def finalize_job_from_report(
    *,
    backtest_id: str,
    report: BacktestReport,
    artifact_store: BacktestArtifactStore,
    job_repository: SqlAlchemyBacktestJobRepository,
    metadata: BacktestListItem | None = None,
    write_artifacts: bool = True,
    artifact_paths: BacktestArtifactPaths | None = None,
) -> BacktestListItem:
    current = metadata.model_copy(deep=True) if metadata is not None else BacktestListItem(
        id=backtest_id,
        created_at=_utc_now(),
        updated_at=_utc_now(),
        status="completed",
        execution_backend="argo",
        total_runs=report.total_runs,
        selection=_selection_from_report(report),
    )
    current.status = "completed" if report.status != "failure" else "failed"
    current.report_status = report.status
    current.completed_runs = report.total_runs
    current.successful_runs = report.successful_runs
    current.failed_runs = report.failed_runs
    current.error_message = None if report.failed_runs == 0 else f"{report.failed_runs} run(s) failed"
    current.updated_at = _utc_now()
    if current.finished_at is None:
        current.finished_at = current.updated_at

    if write_artifacts:
        artifact_store.save_report(backtest_id, report)
        paths = default_artifact_paths(artifact_store.output_dir, backtest_id)
        written = write_report_artifacts(report, paths=paths)
    else:
        written = artifact_paths or BacktestArtifactPaths()

    if job_repository.get(backtest_id) is None:
        job_repository.create(current, paths=written)
    else:
        job_repository.update(current)
        if any(
            (
                written.config_path,
                written.report_json_path,
                written.report_parquet_path,
                written.candidates_json_path,
                written.candidates_parquet_path,
                written.equity_parquet_path,
                written.orders_parquet_path,
                written.trades_parquet_path,
                written.rejections_parquet_path,
                written.manifest_path,
            )
        ):
            job_repository.update_paths(backtest_id, written)
    return current


class BacktestArtifactStore:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self._lock = threading.Lock()

    def ensure_ready(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def report_path(self, backtest_id: str) -> Path:
        return backtest_artifact_dir(self.output_dir, backtest_id) / f"{backtest_id}.json"

    def config_path(self, backtest_id: str) -> Path:
        return backtest_artifact_dir(self.output_dir, backtest_id) / f"{backtest_id}.yaml"

    def artifact_paths(self, backtest_id: str) -> BacktestArtifactPaths:
        return default_artifact_paths(self.output_dir, backtest_id)

    def load_report(self, backtest_id: str, *, report_json_path: str | None = None) -> BacktestReport | None:
        path = Path(report_json_path) if report_json_path else self.report_path(backtest_id)
        if not path.exists():
            return None
        return BacktestReport.model_validate_json(path.read_text(encoding="utf-8"))

    def save_report(self, backtest_id: str, report: BacktestReport) -> None:
        path = self.report_path(backtest_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".tmp")
        write_backtest_report_json(report, temp_path)
        temp_path.replace(path)

    def save_config_yaml(self, backtest_id: str, config_raw: dict[str, Any]) -> None:
        path = self.config_path(backtest_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_suffix(".yaml.tmp")
        temp_path.write_text(config_to_yaml_text(config_raw), encoding="utf-8")
        temp_path.replace(path)

    def resolve_config_yaml(self, backtest_id: str, *, config_path: str | None = None) -> str | None:
        path = Path(config_path) if config_path else self.config_path(backtest_id)
        if path.exists():
            return path.read_text(encoding="utf-8")

        report = self.load_report(backtest_id)
        if report is None or not report.input_config:
            return None
        return config_to_yaml_text(report.input_config)

    def delete_artifacts(self, backtest_id: str, paths: BacktestArtifactPaths | None = None) -> bool:
        resolved_paths = paths or self.artifact_paths(backtest_id)
        candidates = [
            resolved_paths.config_path,
            resolved_paths.report_json_path,
            resolved_paths.report_parquet_path,
            resolved_paths.candidates_json_path,
            resolved_paths.candidates_parquet_path,
            resolved_paths.equity_parquet_path,
            resolved_paths.orders_parquet_path,
            resolved_paths.trades_parquet_path,
            resolved_paths.rejections_parquet_path,
            resolved_paths.manifest_path,
            str(self.report_path(backtest_id)),
            str(self.config_path(backtest_id)),
        ]
        legacy_flat = [
            self.output_dir / f"{backtest_id}.yaml",
            self.output_dir / f"{backtest_id}.json",
            self.output_dir / f"{backtest_id}.parquet",
            self.output_dir / f"{backtest_id}.candidates.json",
            self.output_dir / f"{backtest_id}.candidates.parquet",
            self.output_dir / f"{backtest_id}.equity.parquet",
            self.output_dir / f"{backtest_id}.orders.parquet",
            self.output_dir / f"{backtest_id}.trades.parquet",
            self.output_dir / f"{backtest_id}.rejections.parquet",
        ]
        work_dir = backtest_artifact_dir(self.output_dir, backtest_id)
        deleted = False
        with self._lock:
            for candidate in [*candidates, *[str(path) for path in legacy_flat]]:
                if not candidate:
                    continue
                path = Path(candidate)
                if path.is_file() and path.exists():
                    path.unlink()
                    deleted = True
            if work_dir.is_dir():
                import shutil

                shutil.rmtree(work_dir, ignore_errors=True)
                deleted = True
        return deleted


# Backward-compatible alias for tests and external callers.
BacktestResultRepository = BacktestArtifactStore


class BacktestJobService:
    def __init__(
        self,
        repository: BacktestArtifactStore,
        job_repository: SqlAlchemyBacktestJobRepository,
        cache_config: DataCacheConfig | None = None,
        settings_service: PlatformSettingsService | None = None,
        argo_submitter: ArgoWorkflowSubmitter | None = None,
    ):
        self.repository = repository
        self.job_repository = job_repository
        self.cache_config = cache_config or DataCacheConfig()
        self.settings_service = settings_service
        self.argo_submitter = argo_submitter or ArgoWorkflowSubmitter()

    def _job_exists(self, backtest_id: str) -> bool:
        if self.job_repository.get(backtest_id) is not None:
            return True
        return (
            self.repository.report_path(backtest_id).exists()
            or self.repository.config_path(backtest_id).exists()
        )

    def _platform_settings(self) -> PlatformSettings:
        if self.settings_service is None:
            return PlatformSettings()
        return self.settings_service.load()

    def submit(self, payload: BacktestCreateRequest) -> BacktestCreateResponse:
        platform_settings = self._platform_settings()
        backtest_id = uuid.uuid4().hex
        config = build_backtest_config(payload, backtest_id)
        config_raw = build_backtest_config_raw(payload, backtest_id)
        created_at = _utc_now()
        metadata = BacktestListItem(
            id=backtest_id,
            created_at=created_at,
            updated_at=created_at,
            status="pending",
            total_runs=len(config.runs),
            selection=_build_selection_summary(payload),
        )
        paths = default_artifact_paths(self.repository.output_dir, backtest_id)
        self.job_repository.create(metadata, paths=paths)
        self.repository.save_config_yaml(backtest_id, config_raw)

        if platform_settings.platform_behavior.backtest_execution_backend == "argo":
            split_by = platform_settings.platform_behavior.argo_split_by
            response = self._launch_argo_workflow(
                backtest_id=backtest_id,
                config_path=str(self.repository.config_path(backtest_id).resolve()),
                metadata=metadata,
                split_by=split_by,
                config_raw=config_raw,
            )
            return BacktestCreateResponse(
                backtest_id=response.backtest_id,
                status=response.status,
                status_url=response.status_url,
                detail_url=response.detail_url,
            )

        worker = threading.Thread(
            target=self._run_job,
            args=(metadata, config, config_raw),
            daemon=True,
            name=f"backtest-job-{backtest_id}",
        )
        worker.start()

        return BacktestCreateResponse(
            backtest_id=backtest_id,
            status="pending",
            status_url=f"/backtests/{backtest_id}/status",
            detail_url=f"/backtests/{backtest_id}",
        )

    def submit_argo(self, payload: BacktestArgoLaunchRequest) -> BacktestArgoLaunchResponse:
        if not self.argo_submitter.is_configured:
            raise ArgoNotConfiguredError("Argo Workflows is not configured in this environment")

        platform_settings = self._platform_settings()
        backtest_id = payload.backtest_id or uuid.uuid4().hex
        if self._job_exists(backtest_id):
            raise BacktestAlreadyExistsError(f"Backtest '{backtest_id}' already exists")

        if payload.config_text is not None:
            config_raw = _parse_inline_config(payload.config_text, payload.format)
            BacktestConfig.model_validate(config_raw)
            config_path = self.repository.config_path(backtest_id)
            self.repository.save_config_yaml(backtest_id, config_raw)
            resolved_config_path = str(config_path.resolve())
        else:
            assert payload.config_path is not None
            config_path = Path(payload.config_path)
            if not config_path.is_absolute():
                config_path = (self.repository.output_dir / config_path).resolve()
            if not config_path.exists():
                raise FileNotFoundError(f"Config file not found: {config_path}")
            config_raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if not isinstance(config_raw, dict):
                raise ValueError("Config root must be an object")
            BacktestConfig.model_validate(config_raw)
            resolved_config_path = str(config_path)

        config = BacktestConfig.model_validate(config_raw)
        split_by = resolve_split_by(
            config_raw,
            override=payload.split_by,
            platform_default=platform_settings.platform_behavior.argo_split_by,
        )
        created_at = _utc_now()
        metadata = BacktestListItem(
            id=backtest_id,
            created_at=created_at,
            updated_at=created_at,
            status="pending",
            total_runs=len(config.runs),
            selection=_selection_from_config_raw(config_raw),
            execution_backend="argo",
        )
        paths = default_artifact_paths(self.repository.output_dir, backtest_id)
        self.job_repository.create(metadata, paths=paths)
        return self._launch_argo_workflow(
            backtest_id=backtest_id,
            config_path=resolved_config_path,
            metadata=metadata,
            split_by=split_by,
            config_raw=config_raw,
        )

    def relaunch_argo(self, backtest_id: str, split_by: ArgoSplitBy | None = None) -> BacktestArgoLaunchResponse:
        if not self.repository.config_path(backtest_id).exists():
            raise FileNotFoundError(f"Backtest config '{backtest_id}' not found")
        config_raw = yaml.safe_load(self.repository.config_path(backtest_id).read_text(encoding="utf-8"))
        if not isinstance(config_raw, dict):
            raise ValueError("Config root must be an object")
        metadata = self.job_repository.get(backtest_id)
        if metadata is None:
            config = BacktestConfig.model_validate(config_raw)
            created_at = _utc_now()
            metadata = BacktestListItem(
                id=backtest_id,
                created_at=created_at,
                updated_at=created_at,
                status="pending",
                total_runs=len(config.runs),
                selection=_selection_from_config_raw(config_raw),
                execution_backend="argo",
            )
            paths = default_artifact_paths(self.repository.output_dir, backtest_id)
            self.job_repository.create(metadata, paths=paths)
        else:
            metadata = metadata.model_copy(deep=True)
            metadata.execution_backend = "argo"
            metadata.status = "pending"
            metadata.updated_at = _utc_now()
            metadata.finished_at = None
            self.job_repository.update(metadata)

        platform_settings = self._platform_settings()
        resolved_split = resolve_split_by(
            config_raw,
            override=split_by,
            platform_default=platform_settings.platform_behavior.argo_split_by,
        )
        return self._launch_argo_workflow(
            backtest_id=backtest_id,
            config_path=str(self.repository.config_path(backtest_id).resolve()),
            metadata=metadata,
            split_by=resolved_split,
            config_raw=config_raw,
        )

    def _workflow_volume_paths(self, backtest_id: str) -> tuple[str, str]:
        return workflow_artifact_paths(backtest_id)

    def _ensure_argo_results_visible(self) -> None:
        api_dir = self.repository.output_dir.resolve()
        workflow_dir = Path(workflow_results_mount()).resolve()
        if api_dir == workflow_dir:
            return
        message = (
            f"Argo workflows write results under {workflow_dir}, but this API reads from {api_dir}. "
            "Mount the same shared volume at the same path on the host (e.g. BACKTEST_RESULTS_DIR="
            f"{workflow_dir}) or run the API in-cluster."
        )
        if os.environ.get("ARGO_REQUIRE_SHARED_RESULTS", "").lower() in {"1", "true", "yes"}:
            raise ArgoResultsNotSharedError(message)
        logger.warning(message)

    def _launch_argo_workflow(
        self,
        *,
        backtest_id: str,
        config_path: str,
        metadata: BacktestListItem,
        split_by: ArgoSplitBy,
        config_raw: dict[str, Any],
    ) -> BacktestArgoLaunchResponse:
        if not self.argo_submitter.is_configured:
            raise ArgoNotConfiguredError("Argo Workflows is not configured in this environment")

        self._ensure_argo_results_visible()
        workflow_config_path, workflow_output_path = self._workflow_volume_paths(backtest_id)
        local_config_path = self.repository.config_path(backtest_id)
        source_config_path = local_config_path if local_config_path.exists() else Path(config_path)
        if not source_config_path.exists():
            raise FileNotFoundError(f"Config file not found: {source_config_path}")

        config_yaml = source_config_path.read_text(encoding="utf-8")

        workflow_name, workflow_namespace = self.argo_submitter.submit(
            config_path=workflow_config_path,
            output_path=workflow_output_path,
            split_by=split_by,
            backtest_id=backtest_id,
            config_yaml=config_yaml,
        )

        current = metadata.model_copy(deep=True)
        current.execution_backend = "argo"
        current.workflow_name = workflow_name
        current.workflow_namespace = workflow_namespace
        current.total_runs = len(BacktestConfig.model_validate(config_raw).runs)
        current = _mark_running(current)
        self.job_repository.update(current)

        return BacktestArgoLaunchResponse(
            backtest_id=backtest_id,
            workflow_name=workflow_name,
            status="running",
            status_url=f"/backtests/{backtest_id}/status",
            detail_url=f"/backtests/{backtest_id}",
            workflow_namespace=workflow_namespace,
            config_path=workflow_config_path,
            output_path=workflow_output_path,
        )

    def _refresh_list_item(self, item: BacktestListItem) -> BacktestListItem:
        refreshed = item
        if item.status in {"pending", "running"}:
            if item.execution_backend == "argo" and item.workflow_name:
                from app.backtests.argo_reconciler import reconcile_backtest

                updated = reconcile_backtest(
                    item.id,
                    self.repository,
                    self.job_repository,
                    self.argo_submitter,
                )
                if updated is not None:
                    refreshed = updated
            completed_runs = compute_completed_runs(refreshed, self.repository)
            if completed_runs != refreshed.completed_runs:
                refreshed = refreshed.model_copy(deep=True)
                refreshed.completed_runs = completed_runs
        return self._attach_stored_artifacts(refreshed)

    def _attach_stored_artifacts(self, item: BacktestListItem) -> BacktestListItem:
        if item.status != "completed":
            if item.stored_artifacts:
                return item.model_copy(update={"stored_artifacts": []})
            return item
        paths = self.job_repository.get_paths(item.id)
        stored_artifacts = summarize_backtest_artifacts(
            item.id,
            self.repository.output_dir,
            paths=paths,
        )
        if stored_artifacts == item.stored_artifacts:
            return item
        return item.model_copy(update={"stored_artifacts": stored_artifacts})

    def list_backtests_page(self, *, page: int, page_size: int) -> BacktestListPageResponse:
        total = self.job_repository.count()
        offset = (page - 1) * page_size
        items = self.job_repository.list_recent_page(offset=offset, limit=page_size)
        refreshed = [self._refresh_list_item(item) for item in items]
        return BacktestListPageResponse(
            items=refreshed,
            total=total,
            page=page,
            page_size=page_size,
        )

    def list_backtests(self) -> list[BacktestListItem]:
        total = self.job_repository.count()
        if total == 0:
            return []
        return self.list_backtests_page(page=1, page_size=total).items

    def get_status(self, backtest_id: str) -> BacktestStatusResponse | None:
        metadata = self.job_repository.get(backtest_id)
        if metadata is None:
            return None

        if (
            metadata.execution_backend == "argo"
            and metadata.workflow_name
            and not _is_terminal_status(metadata.status)
        ):
            from app.backtests.argo_reconciler import reconcile_backtest

            updated = reconcile_backtest(
                backtest_id,
                self.repository,
                self.job_repository,
                self.argo_submitter,
            )
            if updated is not None:
                metadata = updated

        completed_runs = compute_completed_runs(metadata, self.repository)
        metadata = self._attach_stored_artifacts(metadata)
        return build_status_response(metadata, completed_runs)

    def resolve_report_file_path(self, backtest_id: str) -> Path | None:
        paths = self.job_repository.get_paths(backtest_id)
        if paths and paths.report_json_path:
            report_path = Path(paths.report_json_path)
            if report_path.is_file():
                return report_path
        fallback = self.repository.report_path(backtest_id)
        return fallback if fallback.is_file() else None

    def resolve_config_yaml_text(self, backtest_id: str) -> str | None:
        paths = self.job_repository.get_paths(backtest_id)
        config_path = paths.config_path if paths else None
        return self.repository.resolve_config_yaml(backtest_id, config_path=config_path)

    def get_detail(self, backtest_id: str) -> BacktestDetailResponse | None:
        metadata = self.job_repository.get(backtest_id)
        if metadata is None:
            return None
        paths = self.job_repository.get_paths(backtest_id)
        report_json_path = paths.report_json_path if paths else None
        report = self.repository.load_report(backtest_id, report_json_path=report_json_path)
        if report is not None and paths is not None:
            report = hydrate_report_from_artifacts(report, paths=paths)
        report_path = self.resolve_report_file_path(backtest_id)
        artifacts = inventory_backtest_artifacts(
            backtest_id,
            self.repository.output_dir,
            paths=paths,
        )
        metadata = self._attach_stored_artifacts(metadata)
        return BacktestDetailResponse(
            metadata=metadata,
            output_path=str(report_path) if report_path is not None else None,
            report=report,
            artifacts=artifacts,
        )

    def delete(self, backtest_id: str) -> bool:
        paths = self.job_repository.get_paths(backtest_id)
        deleted_db = self.job_repository.delete(backtest_id)
        deleted_files = self.repository.delete_artifacts(backtest_id, paths)
        return deleted_db or deleted_files

    def _run_job(self, metadata: BacktestListItem, config: BacktestConfig, config_raw: dict[str, Any]) -> None:
        current = _mark_running(metadata)
        self.job_repository.update(current)

        def mark_progress(result: RunResult) -> None:
            nonlocal current
            current.completed_runs += 1
            if result.status == "success":
                current.successful_runs += 1
            else:
                current.failed_runs += 1
            current.updated_at = _utc_now()
            self.job_repository.update(current)

        try:
            configure_strategy_logging()
            report = run_backtests_with_hooks(
                config,
                config_raw,
                on_run_complete=lambda result, _idx, _total: mark_progress(result),
                on_run_error=lambda result, _idx, _total: mark_progress(result),
                execution_options=RunExecutionOptions(
                    cache_enabled=self.cache_config.enabled,
                    cache_dir=self.cache_config.directory,
                ),
            )
            self.repository.save_config_yaml(current.id, config_raw)
            finalize_job_from_report(
                backtest_id=current.id,
                report=report,
                artifact_store=self.repository,
                job_repository=self.job_repository,
                metadata=current,
            )
        except Exception as exc:  # noqa: BLE001
            current = _mark_terminal(current, status="failed")
            current.error_message = str(exc)
            self.job_repository.update(current)
