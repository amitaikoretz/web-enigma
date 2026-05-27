from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from app.config.models import BacktestConfig
from app.engine.runner import run_backtests
from app.output.models import BacktestReport, CandidateRecord, RunResult, RunSummary
from app.risk.data.report_loader import CandidateLoadError, load_candidates_from_reports
from app.risk.dataset.builder import build_risk_dataset
from app.risk.models import RiskDatasetConfig


def _write_candidate_report(path: Path, candidates: list[CandidateRecord]) -> None:
    report = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="test",
        input_config={
            "runs": [
                {
                    "run_id": "csv_candidates",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-19",
                    "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                    "strategy": "breakout_channel",
                    "strategy_params": {
                        "lookback": 3,
                        "stake": 1.0,
                        "stop_loss_pct": 0.01,
                        "take_profit_pct": 0.02,
                        "max_hold_bars": 5,
                    },
                    "analyzers": {"include_candidate_log": True},
                }
            ]
        },
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="csv_candidates",
                status="success",
                strategy="breakout_channel",
                symbol=None,
                data_source="csv",
                summary=RunSummary(
                    start_value=10_000.0,
                    end_value=10_100.0,
                    return_pct=1.0,
                    total_trades=1,
                    won_trades=1,
                    lost_trades=0,
                ),
                analyzers={"resolution": "1d", "candidate_diagnostics": {"total_candidates": len(candidates)}},
                candidates=candidates,
            )
        ],
    )
    path.write_text(report.model_dump_json(), encoding="utf-8")


def test_load_candidates_fails_when_empty(tmp_path: Path):
    report_path = tmp_path / "empty.json"
    _write_candidate_report(report_path, [])
    with pytest.raises(CandidateLoadError, match="No candidates found"):
        load_candidates_from_reports([report_path])


def test_build_risk_dataset_from_synthetic_report(tmp_path: Path):
    candidates = [
        CandidateRecord(
            candidate_id="abc123",
            strategy_id="breakout_channel",
            symbol="TEST",
            timestamp="2024-01-10T00:00:00+00:00",
            entry_price=102.0,
            planned_stop_pct=0.05,
            planned_target_pct=0.10,
            planned_horizon_bars=3,
            was_traded=False,
            reject_reason="session_window",
        )
    ]
    report_path = tmp_path / "report.json"
    _write_candidate_report(report_path, candidates)

    output_path = tmp_path / "risk_dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(min_history_bars=5, lookback_bars=5, include_index_features=False),
    )
    assert manifest.joined_rows == 1
    assert output_path.exists()

    df = pd.read_parquet(output_path)
    assert len(df) == 1
    assert df.iloc[0]["candidate_id"] == "abc123"
    assert "hit_stop_before_target" in df.columns
    assert "return_20" in df.columns
    assert "label_quality_flag" in df.columns


def test_end_to_end_backtest_json_to_dataset(tmp_path: Path):
    raw = {
        "runs": [
            {
                "run_id": "csv_candidates",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategy": "breakout_channel",
                "strategy_params": {
                    "lookback": 3,
                    "stake": 1.0,
                    "stop_loss_pct": 0.01,
                    "take_profit_pct": 0.02,
                    "max_hold_bars": 5,
                },
                "analyzers": {"include_candidate_log": True},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.results[0].candidates

    report_path = tmp_path / "backtest.json"
    report_path.write_text(json.dumps(json.loads(report.model_dump_json())), encoding="utf-8")

    output_path = tmp_path / "dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(min_history_bars=5, lookback_bars=5, include_index_features=False),
    )
    assert manifest.joined_rows >= 1
    df = pd.read_parquet(output_path)
    assert not df.empty
    assert "label_quality_flag" in df.columns
