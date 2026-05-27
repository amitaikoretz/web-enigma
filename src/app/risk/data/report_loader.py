from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from app.backtests.artifacts import (
    default_artifact_paths,
    hydrate_report_from_artifacts,
    resolve_results_root,
)
from app.output.models import BacktestReport, CandidateRecord, RunResult
from app.risk.models import EnrichedCandidate

logger = logging.getLogger(__name__)


class CandidateLoadError(ValueError):
    pass


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _run_config_for_result(report: BacktestReport, result: RunResult) -> dict[str, Any] | None:
    input_config = report.input_config
    if not isinstance(input_config, dict):
        return None
    runs = input_config.get("runs", [])
    if not isinstance(runs, list):
        return None

    base_run_id = result.run_id.split(":", 1)[0]
    for run in runs:
        if not isinstance(run, dict):
            continue
        run_id = str(run.get("run_id", ""))
        if run_id == result.run_id or run_id == base_run_id:
            return run
    return None


def _strategy_params_from_run(run_cfg: dict[str, Any] | None, strategy_id: str) -> dict[str, Any]:
    if run_cfg is None:
        return {}
    strategies = run_cfg.get("strategies")
    if isinstance(strategies, list):
        for entry in strategies:
            if isinstance(entry, dict) and entry.get("name") == strategy_id:
                params = entry.get("params")
                return dict(params) if isinstance(params, dict) else {}
    params = run_cfg.get("strategy_params")
    return dict(params) if isinstance(params, dict) else {}


def _benchmark_symbol(strategy_id: str, params: dict[str, Any], default: str) -> str | None:
    if strategy_id == "volume_rally":
        symbol = str(params.get("benchmark_symbol", default)).strip().upper()
        return symbol or default
    return None


def _enrich_candidate(
    candidate: CandidateRecord,
    *,
    result: RunResult,
    run_cfg: dict[str, Any] | None,
    source_report_path: str,
    default_benchmark: str,
) -> EnrichedCandidate:
    data = run_cfg.get("data", {}) if isinstance(run_cfg, dict) else {}
    if not isinstance(data, dict):
        data = {}
    execution = run_cfg.get("execution", {}) if isinstance(run_cfg, dict) else {}
    if not isinstance(execution, dict):
        execution = {}

    strategy_params = _strategy_params_from_run(run_cfg, candidate.strategy_id)
    resolution = result.analyzers.get("resolution") if isinstance(result.analyzers, dict) else None
    if resolution is None and isinstance(data, dict):
        resolution = data.get("interval")

    feed = data.get("feed") if isinstance(data, dict) else None
    csv_path = data.get("path") if isinstance(data, dict) and data.get("type") == "csv" else None

    return EnrichedCandidate(
        candidate_id=candidate.candidate_id,
        strategy_id=candidate.strategy_id,
        symbol=candidate.symbol,
        timestamp=candidate.timestamp,
        side=candidate.side,
        entry_price=candidate.entry_price,
        entry_type=candidate.entry_type,
        planned_stop_pct=candidate.planned_stop_pct,
        planned_target_pct=candidate.planned_target_pct,
        planned_horizon_bars=candidate.planned_horizon_bars,
        signal_score=candidate.signal_score,
        signal_reason=candidate.signal_reason,
        metadata=dict(candidate.metadata),
        was_traded=candidate.was_traded,
        reject_reason=candidate.reject_reason,
        run_id=result.run_id,
        resolution=str(resolution) if resolution is not None else None,
        feed=str(feed) if feed is not None else None,
        data_source=result.data_source,
        fill_model=str(execution.get("fill_model", "close")),
        start_date=_parse_date(run_cfg.get("start_date")) if run_cfg else None,
        end_date=_parse_date(run_cfg.get("end_date")) if run_cfg else None,
        benchmark_symbol=_benchmark_symbol(candidate.strategy_id, strategy_params, default_benchmark),
        source_report_path=source_report_path,
        csv_path=str(csv_path) if csv_path else None,
    )


def _validate_candidate(candidate: EnrichedCandidate) -> None:
    if candidate.entry_price <= 0:
        raise CandidateLoadError(f"Candidate {candidate.candidate_id} has invalid entry_price")
    if candidate.planned_stop_pct <= 0:
        raise CandidateLoadError(f"Candidate {candidate.candidate_id} has invalid planned_stop_pct")
    if candidate.planned_horizon_bars <= 0:
        raise CandidateLoadError(f"Candidate {candidate.candidate_id} has invalid planned_horizon_bars")


def load_candidates_from_report(
    report_path: Path,
    *,
    default_benchmark: str = "SPY",
) -> list[EnrichedCandidate]:
    report = BacktestReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    paths = default_artifact_paths(resolve_results_root(report_path), report_path.stem)
    report = hydrate_report_from_artifacts(report, paths=paths)
    enriched: list[EnrichedCandidate] = []
    for result in report.results:
        if result.status != "success":
            continue
        run_cfg = _run_config_for_result(report, result)
        for candidate in result.candidates:
            row = _enrich_candidate(
                candidate,
                result=result,
                run_cfg=run_cfg,
                source_report_path=str(report_path.resolve()),
                default_benchmark=default_benchmark,
            )
            _validate_candidate(row)
            enriched.append(row)
    return enriched


def load_candidates_from_reports(
    report_paths: list[Path],
    *,
    default_benchmark: str = "SPY",
    on_duplicate: str = "keep_first",
) -> tuple[list[EnrichedCandidate], int]:
    merged: list[EnrichedCandidate] = []
    seen: set[str] = set()
    duplicates = 0

    for report_path in report_paths:
        rows = load_candidates_from_report(report_path, default_benchmark=default_benchmark)
        for row in rows:
            if row.candidate_id in seen:
                duplicates += 1
                if on_duplicate == "keep_first":
                    logger.warning("Duplicate candidate_id %s in %s; keeping first", row.candidate_id, report_path)
                    continue
                raise CandidateLoadError(f"Duplicate candidate_id: {row.candidate_id}")
            seen.add(row.candidate_id)
            merged.append(row)

    if not merged:
        raise CandidateLoadError(
            "No candidates found in input report(s). "
            "Ensure backtests were run with analyzers.include_candidate_log: true."
        )
    return merged, duplicates
