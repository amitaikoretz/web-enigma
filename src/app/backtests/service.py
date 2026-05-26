from __future__ import annotations

import json
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.backtests.argo import ArgoWorkflowSubmitter
from app.backtests.models import (
    ArgoSplitBy,
    BacktestArgoLaunchRequest,
    BacktestArgoLaunchResponse,
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestSelectionSummary,
    BacktestStatusResponse,
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


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


class BacktestResultRepository:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self._lock = threading.Lock()

    def ensure_ready(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def report_path(self, backtest_id: str) -> Path:
        return self.output_dir / f"{backtest_id}.json"

    def metadata_path(self, backtest_id: str) -> Path:
        return self.output_dir / f"{backtest_id}.meta.json"

    def config_path(self, backtest_id: str) -> Path:
        return self.output_dir / f"{backtest_id}.yaml"

    def exists(self, backtest_id: str) -> bool:
        return (
            self.metadata_path(backtest_id).exists()
            or self.report_path(backtest_id).exists()
            or self.config_path(backtest_id).exists()
        )

    def write_metadata(self, item: BacktestListItem) -> None:
        self.ensure_ready()
        path = self.metadata_path(item.id)
        with self._lock:
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(item.model_dump_json(indent=2), encoding="utf-8")
            temp_path.replace(path)

    def load_metadata(self, backtest_id: str) -> BacktestListItem | None:
        path = self.metadata_path(backtest_id)
        if not path.exists():
            return None
        return BacktestListItem.model_validate_json(path.read_text(encoding="utf-8"))

    def load_report(self, backtest_id: str) -> BacktestReport | None:
        path = self.report_path(backtest_id)
        if not path.exists():
            return None
        return BacktestReport.model_validate_json(path.read_text(encoding="utf-8"))

    def save_report(self, backtest_id: str, report: BacktestReport) -> None:
        self.ensure_ready()
        path = self.report_path(backtest_id)
        temp_path = path.with_suffix(".tmp")
        write_backtest_report_json(report, temp_path)
        temp_path.replace(path)

    def save_config_yaml(self, backtest_id: str, config_raw: dict[str, Any]) -> None:
        self.ensure_ready()
        path = self.config_path(backtest_id)
        temp_path = path.with_suffix(".yaml.tmp")
        temp_path.write_text(config_to_yaml_text(config_raw), encoding="utf-8")
        temp_path.replace(path)

    def resolve_config_yaml(self, backtest_id: str) -> str | None:
        path = self.config_path(backtest_id)
        if path.exists():
            return path.read_text(encoding="utf-8")

        report = self.load_report(backtest_id)
        if report is None or not report.input_config:
            return None
        return config_to_yaml_text(report.input_config)

    def list_backtests(self) -> list[BacktestListItem]:
        self.ensure_ready()
        ids: set[str] = set()
        for path in self.output_dir.glob("*.meta.json"):
            ids.add(path.name[: -len(".meta.json")])
        for path in self.output_dir.glob("*.json"):
            if path.name.endswith(".meta.json"):
                continue
            ids.add(path.stem)

        items: list[BacktestListItem] = []
        for backtest_id in ids:
            item = self.get_metadata(backtest_id)
            if item is not None:
                items.append(item)

        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def get_metadata(self, backtest_id: str) -> BacktestListItem | None:
        metadata = self.load_metadata(backtest_id)
        if metadata is not None:
            return metadata

        report = self.load_report(backtest_id)
        if report is None:
            return None
        report_path = self.report_path(backtest_id)
        stat = report_path.stat()
        created_at = datetime.fromtimestamp(stat.st_ctime, UTC)
        updated_at = datetime.fromtimestamp(stat.st_mtime, UTC)
        return BacktestListItem(
            id=backtest_id,
            created_at=created_at,
            updated_at=updated_at,
            status="completed",
            report_status=report.status,
            total_runs=report.total_runs,
            completed_runs=report.total_runs,
            successful_runs=report.successful_runs,
            failed_runs=report.failed_runs,
            selection=_selection_from_report(report),
            error_message=None,
        )

    def get_detail(self, backtest_id: str) -> BacktestDetailResponse | None:
        metadata = self.get_metadata(backtest_id)
        if metadata is None:
            return None
        report_path = self.report_path(backtest_id)
        return BacktestDetailResponse(
            metadata=metadata,
            output_path=str(report_path) if report_path.exists() else None,
            report=self.load_report(backtest_id),
        )

    def delete(self, backtest_id: str) -> bool:
        if not self.exists(backtest_id):
            return False
        with self._lock:
            for path in (
                self.report_path(backtest_id),
                self.metadata_path(backtest_id),
                self.config_path(backtest_id),
            ):
                if path.exists():
                    path.unlink()
        return True


class BacktestJobService:
    def __init__(
        self,
        repository: BacktestResultRepository,
        cache_config: DataCacheConfig | None = None,
        settings_service: PlatformSettingsService | None = None,
        argo_submitter: ArgoWorkflowSubmitter | None = None,
    ):
        self.repository = repository
        self.cache_config = cache_config or DataCacheConfig()
        self.settings_service = settings_service
        self.argo_submitter = argo_submitter or ArgoWorkflowSubmitter()

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
        self.repository.write_metadata(metadata)
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
        if self.repository.exists(backtest_id):
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
        self.repository.write_metadata(metadata)
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
        metadata = self.repository.load_metadata(backtest_id)
        if metadata is None:
            config = BacktestConfig.model_validate(config_raw)
            metadata = BacktestListItem(
                id=backtest_id,
                created_at=_utc_now(),
                updated_at=_utc_now(),
                status="pending",
                total_runs=len(config.runs),
                selection=_selection_from_config_raw(config_raw),
                execution_backend="argo",
            )
        else:
            metadata = metadata.model_copy(deep=True)
            metadata.execution_backend = "argo"
            metadata.status = "pending"
            metadata.updated_at = _utc_now()

        platform_settings = self._platform_settings()
        resolved_split = resolve_split_by(
            config_raw,
            override=split_by,
            platform_default=platform_settings.platform_behavior.argo_split_by,
        )
        self.repository.write_metadata(metadata)
        return self._launch_argo_workflow(
            backtest_id=backtest_id,
            config_path=str(self.repository.config_path(backtest_id).resolve()),
            metadata=metadata,
            split_by=resolved_split,
            config_raw=config_raw,
        )

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

        output_path = str(self.repository.report_path(backtest_id).resolve())
        workflow_name, workflow_namespace = self.argo_submitter.submit(
            config_path=config_path,
            output_path=output_path,
            split_by=split_by,
            backtest_id=backtest_id,
        )

        current = metadata.model_copy(deep=True)
        current.execution_backend = "argo"
        current.workflow_name = workflow_name
        current.workflow_namespace = workflow_namespace
        current.status = "running"
        current.total_runs = len(BacktestConfig.model_validate(config_raw).runs)
        current.updated_at = _utc_now()
        self.repository.write_metadata(current)

        return BacktestArgoLaunchResponse(
            backtest_id=backtest_id,
            workflow_name=workflow_name,
            status="running",
            status_url=f"/backtests/{backtest_id}/status",
            detail_url=f"/backtests/{backtest_id}",
            workflow_namespace=workflow_namespace,
            config_path=config_path,
            output_path=output_path,
        )

    def list_backtests(self) -> list[BacktestListItem]:
        return self.repository.list_backtests()

    def get_status(self, backtest_id: str) -> BacktestStatusResponse | None:
        metadata = self.repository.get_metadata(backtest_id)
        if metadata is None:
            return None
        return BacktestStatusResponse(**metadata.model_dump())

    def get_detail(self, backtest_id: str) -> BacktestDetailResponse | None:
        return self.repository.get_detail(backtest_id)

    def delete(self, backtest_id: str) -> bool:
        return self.repository.delete(backtest_id)

    def _run_job(self, metadata: BacktestListItem, config: BacktestConfig, config_raw: dict[str, Any]) -> None:
        current = metadata.model_copy(deep=True)
        current.status = "running"
        current.updated_at = _utc_now()
        self.repository.write_metadata(current)

        def mark_progress(result: RunResult) -> None:
            nonlocal current
            current.completed_runs += 1
            if result.status == "success":
                current.successful_runs += 1
            else:
                current.failed_runs += 1
            current.updated_at = _utc_now()
            self.repository.write_metadata(current)

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
            self.repository.save_report(current.id, report)
            self.repository.save_config_yaml(current.id, config_raw)
        except Exception as exc:  # noqa: BLE001
            current.status = "failed"
            current.error_message = str(exc)
            current.updated_at = _utc_now()
            self.repository.write_metadata(current)
            return

        current.status = "completed"
        current.report_status = report.status
        current.completed_runs = report.total_runs
        current.successful_runs = report.successful_runs
        current.failed_runs = report.failed_runs
        current.error_message = None
        current.updated_at = _utc_now()
        self.repository.write_metadata(current)
