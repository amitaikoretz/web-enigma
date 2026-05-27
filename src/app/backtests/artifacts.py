from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd

from app.backtests.persistence import BacktestArtifactPaths
from app.output.files import write_backtest_report_json
from app.output.models import (
    BacktestReport,
    CandidateRecord,
    EquityPoint,
    OrderRecord,
    RejectionRecord,
    RunResult,
    TradeRecord,
)

RecordT = TypeVar("RecordT")


def persist_backtest_report(report: BacktestReport, output_path: Path) -> BacktestArtifactPaths:
    write_backtest_report_json(report, output_path)
    paths = default_artifact_paths(output_path.parent, output_path.stem)
    return write_report_artifacts(
        report,
        paths=BacktestArtifactPaths(
            config_path=paths.config_path,
            report_json_path=str(output_path.resolve()),
            report_parquet_path=paths.report_parquet_path,
            candidates_parquet_path=paths.candidates_parquet_path,
            equity_parquet_path=paths.equity_parquet_path,
            orders_parquet_path=paths.orders_parquet_path,
            trades_parquet_path=paths.trades_parquet_path,
            rejections_parquet_path=paths.rejections_parquet_path,
            manifest_path=paths.manifest_path,
        ),
    )


def default_artifact_paths(output_dir: Path, backtest_id: str) -> BacktestArtifactPaths:
    base = output_dir.resolve()
    return BacktestArtifactPaths(
        config_path=str(base / f"{backtest_id}.yaml"),
        report_json_path=str(base / f"{backtest_id}.json"),
        report_parquet_path=str(base / f"{backtest_id}.parquet"),
        candidates_json_path=str(base / f"{backtest_id}.candidates.json"),
        candidates_parquet_path=str(base / f"{backtest_id}.candidates.parquet"),
        equity_parquet_path=str(base / f"{backtest_id}.equity.parquet"),
        orders_parquet_path=str(base / f"{backtest_id}.orders.parquet"),
        trades_parquet_path=str(base / f"{backtest_id}.trades.parquet"),
        rejections_parquet_path=str(base / f"{backtest_id}.rejections.parquet"),
        manifest_path=str(base / backtest_id / "manifest.json"),
    )


def _flatten_run_records(
    report: BacktestReport,
    *,
    attr: str,
) -> list[dict]:
    rows: list[dict] = []
    for result in report.results:
        for record in getattr(result, attr):
            payload = record.model_dump(mode="json")
            payload["run_id"] = result.run_id
            rows.append(payload)
    return rows


def _flatten_candidates(report: BacktestReport) -> list[dict]:
    rows: list[dict] = []
    for result in report.results:
        for candidate in result.candidates:
            payload = candidate.model_dump(mode="json")
            payload["run_id"] = result.run_id
            metadata = payload.pop("metadata", {})
            payload["metadata_json"] = json.dumps(metadata) if metadata else None
            rows.append(payload)
    return rows


def _flatten_equity(report: BacktestReport) -> list[dict]:
    rows: list[dict] = []
    for result in report.results:
        for point in result.equity_curve:
            rows.append(
                {
                    "run_id": result.run_id,
                    "datetime": point.datetime,
                    "value": point.value,
                }
            )
    return rows


def _report_summary_rows(report: BacktestReport) -> list[dict]:
    rows: list[dict] = []
    for result in report.results:
        summary = result.summary
        rows.append(
            {
                "run_id": result.run_id,
                "name": result.name,
                "status": result.status,
                "strategy": result.strategy,
                "symbol": result.symbol,
                "data_source": result.data_source,
                "start_value": summary.start_value if summary else None,
                "end_value": summary.end_value if summary else None,
                "return_pct": summary.return_pct if summary else None,
                "max_drawdown_pct": summary.max_drawdown_pct if summary else None,
                "sharpe_ratio": summary.sharpe_ratio if summary else None,
                "total_trades": summary.total_trades if summary else 0,
                "won_trades": summary.won_trades if summary else 0,
                "lost_trades": summary.lost_trades if summary else 0,
            }
        )
    return rows


def _write_parquet(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".parquet.tmp")
    pd.DataFrame(rows).to_parquet(temp_path, index=False)
    temp_path.replace(path)


def _maybe_write_parquet(rows: list[dict], path_value: str | None) -> str | None:
    if not rows or not path_value:
        return None
    _write_parquet(rows, Path(path_value))
    return path_value


def _load_grouped_from_parquet(
    path: Path,
    *,
    model_validate: Callable[[dict], RecordT],
) -> dict[str, list[RecordT]]:
    frame = pd.read_parquet(path)
    if frame.empty:
        return {}
    grouped: dict[str, list[RecordT]] = {}
    for _, row in frame.iterrows():
        run_id = str(row.get("run_id", ""))
        payload = row.to_dict()
        payload.pop("run_id", None)
        grouped.setdefault(run_id, []).append(model_validate(payload))
    return grouped


def write_report_artifacts(
    report: BacktestReport,
    *,
    paths: BacktestArtifactPaths,
) -> BacktestArtifactPaths:
    if paths.report_parquet_path and report.results:
        _write_parquet(_report_summary_rows(report), Path(paths.report_parquet_path))

    candidates_parquet_path = _maybe_write_parquet(
        _flatten_candidates(report),
        paths.candidates_parquet_path,
    )
    equity_parquet_path = _maybe_write_parquet(_flatten_equity(report), paths.equity_parquet_path)
    orders_parquet_path = _maybe_write_parquet(
        _flatten_run_records(report, attr="orders"),
        paths.orders_parquet_path,
    )
    trades_parquet_path = _maybe_write_parquet(
        _flatten_run_records(report, attr="trades"),
        paths.trades_parquet_path,
    )
    rejections_parquet_path = _maybe_write_parquet(
        _flatten_run_records(report, attr="rejections"),
        paths.rejections_parquet_path,
    )

    return BacktestArtifactPaths(
        config_path=paths.config_path,
        report_json_path=paths.report_json_path,
        report_parquet_path=paths.report_parquet_path,
        candidates_json_path=None,
        candidates_parquet_path=candidates_parquet_path,
        equity_parquet_path=equity_parquet_path,
        orders_parquet_path=orders_parquet_path,
        trades_parquet_path=trades_parquet_path,
        rejections_parquet_path=rejections_parquet_path,
        manifest_path=paths.manifest_path,
    )


def load_candidates_from_parquet(path: Path) -> dict[str, list[CandidateRecord]]:
    frame = pd.read_parquet(path)
    if frame.empty:
        return {}
    grouped: dict[str, list[CandidateRecord]] = {}
    for _, row in frame.iterrows():
        run_id = str(row.get("run_id", ""))
        payload = row.to_dict()
        payload.pop("run_id", None)
        metadata_json = payload.pop("metadata_json", None)
        if metadata_json and not pd.isna(metadata_json):
            parsed = json.loads(str(metadata_json))
            payload["metadata"] = parsed if isinstance(parsed, dict) else {}
        else:
            payload["metadata"] = {}
        grouped.setdefault(run_id, []).append(CandidateRecord.model_validate(payload))
    return grouped


def load_equity_from_parquet(path: Path) -> dict[str, list[EquityPoint]]:
    frame = pd.read_parquet(path)
    if frame.empty:
        return {}
    grouped: dict[str, list[EquityPoint]] = {}
    for _, row in frame.iterrows():
        run_id = str(row.get("run_id", ""))
        grouped.setdefault(run_id, []).append(
            EquityPoint(
                datetime=str(row["datetime"]),
                value=float(row["value"]),
            )
        )
    return grouped


def load_orders_from_parquet(path: Path) -> dict[str, list[OrderRecord]]:
    return _load_grouped_from_parquet(path, model_validate=OrderRecord.model_validate)


def load_trades_from_parquet(path: Path) -> dict[str, list[TradeRecord]]:
    return _load_grouped_from_parquet(path, model_validate=TradeRecord.model_validate)


def load_rejections_from_parquet(path: Path) -> dict[str, list[RejectionRecord]]:
    return _load_grouped_from_parquet(path, model_validate=RejectionRecord.model_validate)


def _load_candidates_by_run(paths: BacktestArtifactPaths) -> dict[str, list[CandidateRecord]]:
    if paths.candidates_parquet_path:
        candidate_path = Path(paths.candidates_parquet_path)
        if candidate_path.exists():
            return load_candidates_from_parquet(candidate_path)
    if paths.candidates_json_path:
        json_path = Path(paths.candidates_json_path)
        if json_path.exists():
            candidates_by_run: dict[str, list[CandidateRecord]] = {}
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for entry in raw:
                    if not isinstance(entry, dict):
                        continue
                    run_id = str(entry.pop("run_id", ""))
                    metadata_json = entry.pop("metadata_json", None)
                    if metadata_json and not entry.get("metadata"):
                        parsed = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                        entry["metadata"] = parsed if isinstance(parsed, dict) else {}
                    candidates_by_run.setdefault(run_id, []).append(CandidateRecord.model_validate(entry))
            return candidates_by_run
    return {}


def hydrate_report_from_artifacts(
    report: BacktestReport,
    *,
    paths: BacktestArtifactPaths,
) -> BacktestReport:
    candidates_by_run = _load_candidates_by_run(paths)

    equity_by_run: dict[str, list[EquityPoint]] = {}
    if paths.equity_parquet_path:
        equity_path = Path(paths.equity_parquet_path)
        if equity_path.exists():
            equity_by_run = load_equity_from_parquet(equity_path)

    orders_by_run: dict[str, list[OrderRecord]] = {}
    if paths.orders_parquet_path:
        orders_path = Path(paths.orders_parquet_path)
        if orders_path.exists():
            orders_by_run = load_orders_from_parquet(orders_path)

    trades_by_run: dict[str, list[TradeRecord]] = {}
    if paths.trades_parquet_path:
        trades_path = Path(paths.trades_parquet_path)
        if trades_path.exists():
            trades_by_run = load_trades_from_parquet(trades_path)

    rejections_by_run: dict[str, list[RejectionRecord]] = {}
    if paths.rejections_parquet_path:
        rejections_path = Path(paths.rejections_parquet_path)
        if rejections_path.exists():
            rejections_by_run = load_rejections_from_parquet(rejections_path)

    if not any(
        (
            candidates_by_run,
            equity_by_run,
            orders_by_run,
            trades_by_run,
            rejections_by_run,
        )
    ):
        return report

    hydrated_results: list[RunResult] = []
    for result in report.results:
        updates: dict = {}
        if not result.candidates and result.run_id in candidates_by_run:
            updates["candidates"] = candidates_by_run[result.run_id]
        if not result.equity_curve and result.run_id in equity_by_run:
            updates["equity_curve"] = equity_by_run[result.run_id]
        if not result.orders and result.run_id in orders_by_run:
            updates["orders"] = orders_by_run[result.run_id]
        if not result.trades and result.run_id in trades_by_run:
            updates["trades"] = trades_by_run[result.run_id]
        if not result.rejections and result.run_id in rejections_by_run:
            updates["rejections"] = rejections_by_run[result.run_id]
        if updates:
            hydrated_results.append(result.model_copy(update=updates))
        else:
            hydrated_results.append(result)

    return report.model_copy(update={"results": hydrated_results})
