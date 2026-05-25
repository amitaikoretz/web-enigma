from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from app.backtests.models import (
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestSelectionSummary,
    BacktestStatusResponse,
)
from app.config.models import (
    AnalyzerConfig,
    BacktestConfig,
    DataCacheConfig,
    BrokerConfig,
)
from app.engine.runner import RunExecutionOptions, run_backtests_with_hooks
from app.strategies.auditor_logging import configure_strategy_logging
from app.output import BacktestReport, write_backtest_report_json
from app.output.models import RunResult


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
    def __init__(self, repository: BacktestResultRepository, cache_config: DataCacheConfig | None = None):
        self.repository = repository
        self.cache_config = cache_config or DataCacheConfig()

    def submit(self, payload: BacktestCreateRequest) -> BacktestCreateResponse:
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
