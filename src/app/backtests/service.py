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
    resolve_results_root,
    summarize_backtest_artifacts,
    write_report_artifacts,
)
from app.backtests.replay import build_trade_replay_capsule, build_trade_replay_launch_config
from app.backtests.models import (
    ArgoSplitBy,
    BacktestArgoLaunchRequest,
    BacktestArgoLaunchResponse,
    BacktestConfigUpdateRequest,
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestListItemWithProgress,
    BacktestListPageResponse,
    BacktestRetryRequest,
    BacktestSelectionSummary,
    BacktestTradeReplayResponse,
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


class BacktestJobActiveError(RuntimeError):
    pass


class ArgoResultsNotSharedError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


def _exit_rules_id_from_raw(raw: object) -> str | None:
    if not isinstance(raw, dict):
        return None
    try:
        blob = json.dumps(raw, sort_keys=True, default=str).encode("utf-8")
    except TypeError:
        return None
    import hashlib

    return hashlib.sha1(blob).hexdigest()[:10]  # noqa: S324


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _merge_artifact_paths(
    preferred: BacktestArtifactPaths | None,
    fallback: BacktestArtifactPaths,
) -> BacktestArtifactPaths:
    if preferred is None:
        return fallback

    def _prefer_existing(value: str | None, default: str | None) -> str | None:
        if value and Path(value).is_file():
            return value
        if default and Path(default).is_file():
            return default
        return value or default

    return BacktestArtifactPaths(
        config_path=_prefer_existing(preferred.config_path, fallback.config_path),
        report_json_path=_prefer_existing(preferred.report_json_path, fallback.report_json_path),
        report_parquet_path=_prefer_existing(preferred.report_parquet_path, fallback.report_parquet_path),
        candidates_json_path=_prefer_existing(preferred.candidates_json_path, fallback.candidates_json_path),
        candidates_parquet_path=_prefer_existing(preferred.candidates_parquet_path, fallback.candidates_parquet_path),
        equity_parquet_path=_prefer_existing(preferred.equity_parquet_path, fallback.equity_parquet_path),
        orders_parquet_path=_prefer_existing(preferred.orders_parquet_path, fallback.orders_parquet_path),
        trades_parquet_path=_prefer_existing(preferred.trades_parquet_path, fallback.trades_parquet_path),
        rejections_parquet_path=_prefer_existing(preferred.rejections_parquet_path, fallback.rejections_parquet_path),
        labels_parquet_path=_prefer_existing(preferred.labels_parquet_path, fallback.labels_parquet_path),
        features_parquet_path=_prefer_existing(preferred.features_parquet_path, fallback.features_parquet_path),
        manifest_path=_prefer_existing(preferred.manifest_path, fallback.manifest_path),
    )


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
        triggers=[trigger.name for trigger in payload.triggers],
        exit_rules=[rules.stable_id() for rules in payload.exit_rules],
    )


def _selection_from_report(report: BacktestReport) -> BacktestSelectionSummary:
    input_config = report.input_config
    runs = input_config.get("runs", []) if isinstance(input_config, dict) else []
    symbols: list[str] = []
    triggers: list[str] = []
    exit_rules: list[str] = []
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
        trigger = run.get("trigger")
        if isinstance(trigger, dict):
            name = trigger.get("name")
            if isinstance(name, str) and name not in triggers:
                triggers.append(name)
        exits = run.get("exit_rules")
        rules_id = _exit_rules_id_from_raw(exits)
        if rules_id and rules_id not in exit_rules:
            exit_rules.append(rules_id)

    return BacktestSelectionSummary(
        start_date=start_date,
        end_date=end_date,
        resolution=resolution,
        feed=feed,
        symbols=symbols,
        triggers=triggers,
        exit_rules=exit_rules,
    )


def _file_timestamp(path: Path | None) -> datetime:
    if path is None or not path.exists():
        return _utc_now()
    return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)


def _metadata_from_report(
    backtest_id: str,
    report: BacktestReport,
    *,
    report_path: Path | None,
    config_path: Path | None,
) -> BacktestListItem:
    timestamp = max(_file_timestamp(report_path), _file_timestamp(config_path))
    status = "completed" if report.status != "failure" else "failed"
    error_message = None if report.failed_runs == 0 else f"{report.failed_runs} run(s) failed"
    return BacktestListItem(
        id=backtest_id,
        created_at=timestamp,
        updated_at=timestamp,
        status=status,
        report_status=report.status,
        total_runs=report.total_runs,
        completed_runs=report.total_runs,
        successful_runs=report.successful_runs,
        failed_runs=report.failed_runs,
        selection=_selection_from_report(report),
        error_message=error_message,
        execution_backend="local",
        started_at=report.generated_at,
        finished_at=report.generated_at,
    )


def _selection_from_config_raw(config_raw: dict[str, Any]) -> BacktestSelectionSummary | None:
    runs = config_raw.get("runs")
    if not isinstance(runs, list) or not runs:
        return None
    symbols: list[str] = []
    triggers: list[str] = []
    exit_rules: list[str] = []
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
        trigger = run.get("trigger")
        if isinstance(trigger, dict):
            name = trigger.get("name")
            if isinstance(name, str) and name not in triggers:
                triggers.append(name)
        exits = run.get("exit_rules")
        rules_id = _exit_rules_id_from_raw(exits)
        if rules_id and rules_id not in exit_rules:
            exit_rules.append(rules_id)

    if start_date is None or end_date is None:
        return None
    return BacktestSelectionSummary(
        start_date=start_date,
        end_date=end_date,
        resolution=resolution,
        feed=feed,  # type: ignore[arg-type]
        symbols=symbols or ["UNKNOWN"],
        triggers=triggers or ["unknown"],
        exit_rules=exit_rules or ["unknown"],
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
    model_policy = payload.model_policy
    model_policy_id = model_policy.stable_id() if model_policy is not None else None
    runs: list[dict[str, Any]] = []

    for trigger in payload.triggers:
        for exit_rules in payload.exit_rules:
            exits_id = exit_rules.stable_id()
            for symbol in payload.symbols:
                run_index = len(runs) + 1
                run_id_parts = [backtest_id, f"{run_index:03d}", symbol, trigger.name, f"exits:{exits_id}"]
                if model_policy_id is not None:
                    run_id_parts.append(f"models:{model_policy_id}")
                run_id = ":".join(run_id_parts)
                run_name_parts = [symbol, trigger.name, f"exits:{exits_id}"]
                if model_policy_id is not None:
                    run_name_parts.append(f"models:{model_policy_id}")
                run_payload: dict[str, Any] = {
                    "run_id": run_id,
                    "name": " ".join(run_name_parts),
                    "start_date": payload.start_date.isoformat(),
                    "end_date": payload.end_date.isoformat(),
                    "data": {
                        "type": "alpaca",
                        "symbol": symbol,
                        "interval": payload.resolution,
                        "feed": payload.feed,
                    },
                    "trigger": trigger.model_dump(mode="json"),
                    "exit_rules": exit_rules.model_dump(mode="json"),
                    "broker": broker.model_dump(mode="json"),
                    "analyzers": analyzers.model_dump(mode="json"),
                }
                if model_policy is not None:
                    run_payload["model_policy"] = model_policy.model_dump(mode="json")
                if execution is not None:
                    run_payload["execution"] = execution.model_dump(mode="json")
                runs.append(run_payload)

    return {"runs": runs}


def build_backtest_config(payload: BacktestCreateRequest, backtest_id: str) -> BacktestConfig:
    return BacktestConfig.model_validate(build_backtest_config_raw(payload, backtest_id))


def _run_symbol_from_config(run: dict[str, Any]) -> str:
    data = run.get("data")
    if isinstance(data, dict):
        symbol = data.get("symbol")
        if isinstance(symbol, str) and symbol:
            return symbol
    return "UNKNOWN"


def _run_trigger_from_config(run: dict[str, Any]) -> str:
    trigger = run.get("trigger")
    if isinstance(trigger, dict):
        name = trigger.get("name")
        if isinstance(name, str) and name:
            return name
    return "unknown_trigger"


def _rewrite_run_ids(config_raw: dict[str, Any], new_backtest_id: str) -> dict[str, Any]:
    cloned = json.loads(json.dumps(config_raw))
    runs = cloned.get("runs")
    if not isinstance(runs, list):
        raise ValueError("Config must contain a runs array")
    for run_index, run in enumerate(runs, start=1):
        if not isinstance(run, dict):
            continue
        symbol = _run_symbol_from_config(run)
        trigger = _run_trigger_from_config(run)
        run["run_id"] = f"{new_backtest_id}:{run_index:03d}:{symbol}:{trigger}"
    return cloned


def _is_terminal_status(status: str) -> bool:
    return status in {"completed", "failed"}


def _progress_pct(
    completed_runs: int,
    total_runs: int,
    status: str,
    *,
    fallback_pct: float | None = None,
) -> float:
    if total_runs == 0:
        return 0.0
    if status == "completed":
        return 100.0
    progress = min(100.0, (completed_runs / total_runs) * 100.0)
    if fallback_pct is not None:
        progress = max(progress, min(100.0, fallback_pct))
    return progress


def compute_completed_runs(
    metadata: BacktestListItem,
    repository: BacktestArtifactStore,
    *,
    workflow: dict | None = None,
) -> int:
    from app.backtests.argo_progress_status import blend_completed_runs

    completed_runs, _fallback_pct = blend_completed_runs(
        metadata,
        repository.output_dir,
        workflow=workflow,
    )
    return completed_runs


def build_status_response(
    metadata: BacktestListItem,
    completed_runs: int,
    *,
    fallback_pct: float | None = None,
) -> BacktestStatusResponse:
    progress = _progress_pct(
        completed_runs,
        metadata.total_runs,
        metadata.status,
        fallback_pct=fallback_pct,
    )
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
    risk_auxiliary_by_run: dict | None = None,
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
        label_rows: list[dict] = []
        feature_rows: list[dict] = []
        if risk_auxiliary_by_run:
            from app.backtests.artifacts import flatten_risk_auxiliary_for_report

            label_rows, feature_rows = flatten_risk_auxiliary_for_report(report, risk_auxiliary_by_run)
        written = write_report_artifacts(
            report,
            paths=paths,
            label_rows=label_rows,
            feature_rows=feature_rows,
        )
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
                written.labels_parquet_path,
                written.features_parquet_path,
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
            resolved_paths.labels_parquet_path,
            resolved_paths.features_parquet_path,
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
            self.output_dir / f"{backtest_id}.labels.parquet",
            self.output_dir / f"{backtest_id}.features.parquet",
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
        backtest_id = uuid.uuid4().hex
        config_raw = build_backtest_config_raw(payload, backtest_id)
        return self._submit_from_config_raw(
            config_raw,
            backtest_id,
            selection=_build_selection_summary(payload),
            name=payload.name,
        )

    def retry_backtest(
        self,
        source_backtest_id: str,
        payload: BacktestRetryRequest | None = None,
    ) -> BacktestCreateResponse:
        config_path = self.repository.config_path(source_backtest_id)
        if not config_path.exists():
            raise FileNotFoundError(f"Backtest config '{source_backtest_id}' not found")

        source = self.job_repository.get(source_backtest_id)
        force = bool(payload.force) if payload is not None else False
        if source is not None and source.status in {"pending", "running"} and not force:
            raise BacktestJobActiveError(f"Backtest '{source_backtest_id}' is still active")

        if payload is not None and payload.config_text is not None:
            config_raw = _parse_inline_config(payload.config_text, payload.format)
        else:
            config_raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if not isinstance(config_raw, dict):
                raise ValueError("Config root must be an object")

        new_id = uuid.uuid4().hex
        config_raw = _rewrite_run_ids(config_raw, new_id)
        BacktestConfig.model_validate(config_raw)
        return self._submit_from_config_raw(
            config_raw,
            new_id,
            source_backtest_id=source_backtest_id,
        )

    def update_config(self, backtest_id: str, payload: BacktestConfigUpdateRequest) -> BacktestListItem:
        existing = self.job_repository.get(backtest_id)
        if existing is None:
            raise FileNotFoundError(f"Backtest '{backtest_id}' not found")
        config_raw = _parse_inline_config(payload.config_text, payload.format)
        BacktestConfig.model_validate(config_raw)
        self.repository.save_config_yaml(backtest_id, config_raw)
        selection = _selection_from_config_raw(config_raw)
        updated = existing.model_copy(deep=True)
        updated.selection = selection or updated.selection
        updated.updated_at = _utc_now()
        self.job_repository.update(updated)
        return updated

    def _submit_from_config_raw(
        self,
        config_raw: dict[str, Any],
        backtest_id: str,
        *,
        selection: BacktestSelectionSummary | None = None,
        source_backtest_id: str | None = None,
        name: str | None = None,
    ) -> BacktestCreateResponse:
        platform_settings = self._platform_settings()
        config = BacktestConfig.model_validate(config_raw)
        created_at = _utc_now()
        execution_backend = platform_settings.platform_behavior.backtest_execution_backend
        metadata = BacktestListItem(
            id=backtest_id,
            name=name,
            created_at=created_at,
            updated_at=created_at,
            status="pending",
            total_runs=len(config.runs),
            selection=selection or _selection_from_config_raw(config_raw),
            execution_backend=execution_backend,
        )
        results_root = self.repository.output_dir
        if execution_backend == "argo":
            results_root = Path(workflow_results_mount())
        paths = default_artifact_paths(results_root, backtest_id)
        self.job_repository.create(metadata, paths=paths)
        self.repository.save_config_yaml(backtest_id, config_raw)

        if execution_backend == "argo":
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
                source_backtest_id=source_backtest_id,
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
            source_backtest_id=source_backtest_id,
        )

    def submit_argo(self, payload: BacktestArgoLaunchRequest) -> BacktestArgoLaunchResponse:
        if not self.argo_submitter.is_configured:
            raise ArgoNotConfiguredError(
                "Argo Workflows is not configured: set ARGO_SERVER_URL to the Argo server HTTP endpoint"
            )

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
        paths = default_artifact_paths(Path(workflow_results_mount()), backtest_id)
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
            paths = default_artifact_paths(Path(workflow_results_mount()), backtest_id)
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
            raise ArgoNotConfiguredError(
                "Argo Workflows is not configured: set ARGO_SERVER_URL to the Argo server HTTP endpoint"
            )

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

    def _fetch_argo_workflow(self, metadata: BacktestListItem) -> dict | None:
        if (
            metadata.execution_backend != "argo"
            or not metadata.workflow_name
            or _is_terminal_status(metadata.status)
            or not self.argo_submitter.is_configured
        ):
            return None
        return self.argo_submitter.get_workflow(metadata.workflow_name)

    def _resolve_running_progress(
        self,
        metadata: BacktestListItem,
        *,
        workflow: dict | None = None,
    ) -> tuple[int, float | None]:
        from app.backtests.argo_progress_status import blend_completed_runs

        return blend_completed_runs(
            metadata,
            self.repository.output_dir,
            workflow=workflow,
        )

    def _refresh_list_item(self, item: BacktestListItem) -> BacktestListItem:
        refreshed = item
        workflow = None
        if item.status in {"pending", "running"}:
            if item.execution_backend == "argo" and item.workflow_name:
                from app.backtests.argo_reconciler import reconcile_backtest

                workflow = self._fetch_argo_workflow(item)
                updated = reconcile_backtest(
                    item.id,
                    self.repository,
                    self.job_repository,
                    self.argo_submitter,
                    workflow=workflow,
                )
                if updated is not None:
                    refreshed = updated
            completed_runs, _fallback_pct = self._resolve_running_progress(refreshed, workflow=workflow)
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
        refreshed: list[BacktestListItemWithProgress] = []
        for item in items:
            updated = self._refresh_list_item(item)

            workflow = None
            if (
                updated.execution_backend == "argo"
                and updated.workflow_name
                and updated.status in {"pending", "running"}
                and self.argo_submitter.is_configured
            ):
                workflow = self._fetch_argo_workflow(updated)

            completed_runs, fallback_pct = self._resolve_running_progress(updated, workflow=workflow)
            progress = _progress_pct(
                completed_runs,
                updated.total_runs,
                updated.status,
                fallback_pct=fallback_pct,
            )
            progress_source = "argo" if fallback_pct is not None else "runs"
            refreshed.append(
                BacktestListItemWithProgress(
                    **updated.model_dump(),
                    progress_pct=progress,
                    progress_source=progress_source,
                )
            )
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
            report_path = self.resolve_report_file_path(backtest_id)
            report = (
                self.repository.load_report(backtest_id, report_json_path=str(report_path))
                if report_path is not None
                else None
            )
            if report is None:
                return None
            config_path = self.job_repository.get_paths(backtest_id)
            metadata = _metadata_from_report(
                backtest_id,
                report,
                report_path=report_path,
                config_path=Path(config_path.config_path) if config_path and config_path.config_path else None,
            )
        if metadata is None:
            return None

        workflow = None
        if (
            metadata.execution_backend == "argo"
            and metadata.workflow_name
            and not _is_terminal_status(metadata.status)
        ):
            from app.backtests.argo_reconciler import reconcile_backtest

            workflow = self._fetch_argo_workflow(metadata)
            updated = reconcile_backtest(
                backtest_id,
                self.repository,
                self.job_repository,
                self.argo_submitter,
                workflow=workflow,
            )
            if updated is not None:
                metadata = updated

        completed_runs, fallback_pct = self._resolve_running_progress(metadata, workflow=workflow)
        metadata = self._attach_stored_artifacts(metadata)
        if completed_runs != metadata.completed_runs:
            metadata = metadata.model_copy(deep=True)
            metadata.completed_runs = completed_runs
        return build_status_response(metadata, completed_runs, fallback_pct=fallback_pct)

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
        paths = self.job_repository.get_paths(backtest_id)
        report_path = self.resolve_report_file_path(backtest_id)
        if metadata is None:
            report = (
                self.repository.load_report(backtest_id, report_json_path=str(report_path))
                if report_path is not None
                else None
            )
            if report is None:
                return None
            metadata = _metadata_from_report(
                backtest_id,
                report,
                report_path=report_path,
                config_path=Path(paths.config_path) if paths and paths.config_path else None,
            )
        hydrate_paths = paths
        if report_path is not None:
            fallback_paths = default_artifact_paths(resolve_results_root(report_path, backtest_id), backtest_id)
            hydrate_paths = _merge_artifact_paths(paths, fallback_paths)
        report = (
            self.repository.load_report(backtest_id, report_json_path=str(report_path))
            if report_path is not None
            else None
        )
        if report is not None:
            report = hydrate_report_from_artifacts(
                report,
                paths=hydrate_paths or default_artifact_paths(self.repository.output_dir, backtest_id),
            )
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

    def get_trade_replay(self, backtest_id: str, run_id: str, trade_index: int) -> BacktestTradeReplayResponse:
        detail = self.get_detail(backtest_id)
        if detail is None:
            raise FileNotFoundError(f"Backtest '{backtest_id}' not found")
        capsule = build_trade_replay_capsule(detail, run_id=run_id, trade_index=trade_index)
        return BacktestTradeReplayResponse(
            capsule=capsule,
            launch_config=build_trade_replay_launch_config(capsule),
        )

    def update_name(self, backtest_id: str, name: str | None) -> BacktestListItem:
        current = self.job_repository.get(backtest_id)
        if current is None:
            raise FileNotFoundError(f"Backtest '{backtest_id}' not found")
        updated = current.model_copy(deep=True)
        updated.name = name
        updated.updated_at = _utc_now()
        self.job_repository.update(updated)
        return self._attach_stored_artifacts(updated)

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
            execution = run_backtests_with_hooks(
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
                report=execution.report,
                artifact_store=self.repository,
                job_repository=self.job_repository,
                metadata=current,
                risk_auxiliary_by_run=execution.risk_auxiliary_by_run,
            )
        except Exception as exc:  # noqa: BLE001
            current = _mark_terminal(current, status="failed")
            current.error_message = str(exc)
            self.job_repository.update(current)
