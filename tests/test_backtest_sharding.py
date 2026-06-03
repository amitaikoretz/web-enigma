from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

from app.backtests.artifacts import persist_backtest_report
from app.backtests.merge import merge_exit_code, merge_shard_reports
from app.backtests.sharding import plan_shards, resolve_split_by, write_shard_manifest
from app.config.models import BacktestConfig
from app.output.models import BacktestReport, CandidateRecord, RunResult, RunSummary


def _sample_config_raw() -> dict:
    return {
        "global_config": {"timezone": "UTC"},
        "runs": [
            {
                "run_id": "aapl_sma",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "yahoo", "symbol": "AAPL", "interval": "1d"},
                "trigger": {"name": "sma_cross", "params": {"fast": 3, "slow": 8, "stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 24}}]},
            },
            {
                "run_id": "msft_sma",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "yahoo", "symbol": "MSFT", "interval": "1d"},
                "trigger": {"name": "sma_cross", "params": {"fast": 3, "slow": 8, "stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 24}}]},
            },
            {
                "run_id": "aapl_rsi",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "yahoo", "symbol": "AAPL", "interval": "1d"},
                "trigger": {"name": "rsi_reversion", "params": {"period": 7, "oversold": 30, "stake": 1}},
                "exit_rules": {"rules": [{"name": "rsi_overbought", "params": {"period": 7, "overbought": 60}}]},
            },
        ],
    }


def _fake_report(run_id: str, status: str = "success") -> BacktestReport:
    return BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="test",
        config_sha256="abc",
        total_runs=1,
        successful_runs=1 if status == "success" else 0,
        failed_runs=0 if status == "success" else 1,
        status="success" if status == "success" else "failure",
        results=[
            RunResult(
                run_id=run_id,
                status=status,  # type: ignore[arg-type]
                strategy="sma_cross",
                symbol="AAPL",
                data_source="csv",
                summary=RunSummary(start_value=10000, end_value=10050, return_pct=0.5),
            )
        ],
    )


def test_resolve_split_by_yaml_override():
    raw = {"workflow": {"split_by": "symbol"}, "runs": []}
    assert resolve_split_by(raw, platform_default="symbol_trigger") == "symbol"


def test_resolve_split_by_accepts_strategy_aliases():
    raw = {"workflow": {"split_by": "symbol_strategy"}, "runs": []}
    assert resolve_split_by(raw, platform_default="run") == "symbol_trigger"


def test_resolve_split_by_platform_default():
    raw = {"runs": []}
    assert resolve_split_by(raw, platform_default="run") == "run"


def test_plan_shards_by_run(tmp_path: Path):
    raw = _sample_config_raw()
    BacktestConfig.model_validate(raw)
    plan = plan_shards(raw, split_by="run", work_dir=tmp_path)
    assert len(plan.shards) == 3
    assert all(Path(shard.config_path).exists() for shard in plan.shards)


def test_plan_shards_by_symbol(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="symbol", work_dir=tmp_path)
    assert len(plan.shards) == 2
    counts = sorted(len(yaml.safe_load(Path(s.config_path).read_text())["runs"]) for s in plan.shards)
    assert counts == [1, 2]


def test_plan_shards_by_trigger(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="trigger", work_dir=tmp_path)
    assert len(plan.shards) == 2
    counts = sorted(len(yaml.safe_load(Path(s.config_path).read_text())["runs"]) for s in plan.shards)
    assert counts == [1, 2]


def test_plan_shards_by_strategy_alias(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="strategy", work_dir=tmp_path)
    assert len(plan.shards) == 2
    counts = sorted(len(yaml.safe_load(Path(s.config_path).read_text())["runs"]) for s in plan.shards)
    assert counts == [1, 2]


def test_plan_shards_symbol_trigger(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="symbol_trigger", work_dir=tmp_path)
    assert len(plan.shards) == 3


def test_plan_shards_symbol_strategy_alias(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="symbol_strategy", work_dir=tmp_path)
    assert len(plan.shards) == 3


def test_merge_shard_reports(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="run", work_dir=tmp_path)
    for shard in plan.shards:
        report = _fake_report(shard.shard_id)
        Path(shard.output_path).write_text(report.model_dump_json(), encoding="utf-8")
    merged = merge_shard_reports(plan, original_config_raw=raw)
    assert merged.total_runs == 3
    assert merged.successful_runs == 3
    assert merged.status == "success"
    assert merge_exit_code(merged) == 0


def test_merge_shard_reports_hydrates_candidates_from_shard_sidecars(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="run", work_dir=tmp_path)
    for shard in plan.shards:
        report = BacktestReport(
            generated_at=datetime.now(UTC),
            app_version="test",
            config_sha256="abc",
            total_runs=1,
            successful_runs=1,
            failed_runs=0,
            status="success",
            results=[
                RunResult(
                    run_id=shard.shard_id,
                    status="success",
                    strategy="sma_cross",
                    symbol="AAPL",
                    data_source="csv",
                    summary=RunSummary(start_value=10000, end_value=10050, return_pct=0.5),
                    candidates=[
                        CandidateRecord(
                            candidate_id=f"{shard.shard_id}-cand",
                            strategy_id="sma_cross",
                            symbol="AAPL",
                            timestamp="2024-01-02T00:00:00+00:00",
                            entry_price=100.0,
                            planned_stop_pct=0.02,
                            planned_horizon_bars=10,
                            was_traded=True,
                        )
                    ],
                )
            ],
        )
        persist_backtest_report(report, Path(shard.output_path))

    merged = merge_shard_reports(plan, original_config_raw=raw)
    assert len(merged.results) == 3
    assert merged.results[0].candidates
    assert merged.results[0].candidates[0].candidate_id.endswith("-cand")


def test_merge_partial_failure(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="run", work_dir=tmp_path)
    for index, shard in enumerate(plan.shards):
        status = "success" if index < 2 else "failed"
        report = _fake_report(shard.shard_id, status=status)
        Path(shard.output_path).write_text(report.model_dump_json(), encoding="utf-8")
    merged = merge_shard_reports(plan, original_config_raw=raw)
    assert merged.status == "partial_failure"
    assert merge_exit_code(merged) == 10


def test_write_and_load_manifest(tmp_path: Path):
    raw = _sample_config_raw()
    plan = plan_shards(raw, split_by="run", work_dir=tmp_path)
    manifest_path = tmp_path / "manifest.json"
    write_shard_manifest(plan, manifest_path)
    loaded = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert loaded["split_by"] == "run"
    assert len(loaded["shards"]) == 3
