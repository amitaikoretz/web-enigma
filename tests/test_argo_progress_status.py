from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from app.backtests.argo_progress import parse_argo_progress, progress_fraction
from app.backtests.argo_progress_status import (
    blend_completed_runs,
    compute_argo_weighted_completed_runs,
    index_run_shard_nodes,
)
from app.backtests.models import BacktestListItem
from app.backtests.sharding import ShardPlan, ShardSpec, write_shard_manifest
from app.output.models import BacktestReport


def test_parse_argo_progress_valid() -> None:
    assert parse_argo_progress("50/100") == (50, 100)
    assert parse_argo_progress("  7/10\n") == (7, 10)
    assert parse_argo_progress("1/3\n50/100\n") == (50, 100)


def test_parse_argo_progress_invalid() -> None:
    assert parse_argo_progress("") is None
    assert parse_argo_progress("invalid") is None
    assert parse_argo_progress("-1/10") is None


def test_progress_fraction() -> None:
    assert progress_fraction(0, 0) == 0.0
    assert progress_fraction(50, 100) == 0.5
    assert progress_fraction(150, 100) == 1.0


def test_index_run_shard_nodes() -> None:
    nodes = {
        "node-1": {
            "templateName": "plan-shards",
            "progress": "1/1",
        },
        "node-2": {
            "templateName": "run-shard",
            "progress": "50/100",
            "inputs": {
                "parameters": [
                    {"name": "shard-id", "value": "aapl"},
                    {"name": "shard-output-path", "value": "/data/shards/aapl.json"},
                ]
            },
        },
    }
    by_output, by_shard_id = index_run_shard_nodes(nodes)
    assert by_output["/data/shards/aapl.json"]["progress"] == "50/100"
    assert by_shard_id["aapl"]["progress"] == "50/100"


def test_compute_argo_weighted_completed_runs_with_partial_shard(tmp_path: Path) -> None:
    shards_dir = tmp_path / "shards"
    shards_dir.mkdir()
    done_output = shards_dir / "done.json"
    pending_output = shards_dir / "pending.json"
    done_config = shards_dir / "done.yaml"
    pending_config = shards_dir / "pending.yaml"

    done_config.write_text(
        yaml.safe_dump(
            {
                "global_config": {"execution": {"fill_model": "close"}},
                "runs": [
                    {
                        "run_id": "r1",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                    {
                        "run_id": "r2",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    pending_config.write_text(
        yaml.safe_dump(
            {
                "global_config": {"execution": {"fill_model": "close"}},
                "runs": [
                    {
                        "run_id": "r3",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                    {
                        "run_id": "r4",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                    {
                        "run_id": "r5",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                    {
                        "run_id": "r6",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    done_output.write_text(
        BacktestReport(
            generated_at=datetime.now(UTC),
            app_version="0.1.0",
            config_sha256="abc",
            input_config={},
            total_runs=2,
            successful_runs=2,
            failed_runs=0,
            status="success",
            results=[],
        ).model_dump_json(),
        encoding="utf-8",
    )

    plan = ShardPlan(
        config_path=str(tmp_path / "original.yaml"),
        split_by="symbol",
        shards=[
            ShardSpec(shard_id="done", config_path=str(done_config), output_path=str(done_output)),
            ShardSpec(shard_id="pending", config_path=str(pending_config), output_path=str(pending_output)),
        ],
    )
    nodes = {
        "pending-node": {
            "templateName": "run-shard",
            "phase": "Running",
            "progress": "50/100",
            "inputs": {
                "parameters": [
                    {"name": "shard-id", "value": "pending"},
                    {"name": "shard-output-path", "value": str(pending_output)},
                ]
            },
        }
    }

    weighted = compute_argo_weighted_completed_runs(plan, nodes)
    assert weighted == 2.0


def test_compute_argo_weighted_completed_runs_mid_run_progress(tmp_path: Path) -> None:
    shards_dir = tmp_path / "shards"
    shards_dir.mkdir()
    pending_output = shards_dir / "pending.json"
    pending_config = shards_dir / "pending.yaml"
    pending_config.write_text(
        yaml.safe_dump(
            {
                "global_config": {"execution": {"fill_model": "close"}},
                "runs": [
                    {
                        "run_id": f"r{i}",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    }
                    for i in range(1, 5)
                ],
            }
        ),
        encoding="utf-8",
    )
    plan = ShardPlan(
        config_path=str(tmp_path / "original.yaml"),
        split_by="symbol",
        shards=[
            ShardSpec(shard_id="pending", config_path=str(pending_config), output_path=str(pending_output)),
        ],
    )
    nodes = {
        "pending-node": {
            "templateName": "run-shard",
            "phase": "Running",
            "progress": "37/100",
            "inputs": {
                "parameters": [
                    {"name": "shard-id", "value": "pending"},
                    {"name": "shard-output-path", "value": str(pending_output)},
                ]
            },
        }
    }

    weighted = compute_argo_weighted_completed_runs(plan, nodes)

    assert weighted == pytest.approx(1.48)
    backtest_id = "blend-test"
    work_dir = tmp_path / backtest_id
    shards_dir = work_dir / "shards"
    shards_dir.mkdir(parents=True)
    done_output = shards_dir / "done.json"
    pending_output = shards_dir / "pending.json"
    done_config = shards_dir / "done.yaml"
    pending_config = shards_dir / "pending.yaml"

    done_config.write_text(
        yaml.safe_dump(
            {
                "global_config": {"execution": {"fill_model": "close"}},
                "runs": [
                    {
                        "run_id": "r1",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                    {
                        "run_id": "r2",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    pending_config.write_text(
        yaml.safe_dump(
            {
                "global_config": {"execution": {"fill_model": "close"}},
                "runs": [
                    {
                        "run_id": "r3",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                    {
                        "run_id": "r4",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                    {
                        "run_id": "r5",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                    {
                        "run_id": "r6",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "strategy": "buy_and_hold",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    done_output.write_text(
        BacktestReport(
            generated_at=datetime.now(UTC),
            app_version="0.1.0",
            config_sha256="abc",
            input_config={},
            total_runs=2,
            successful_runs=2,
            failed_runs=0,
            status="success",
            results=[],
        ).model_dump_json(),
        encoding="utf-8",
    )
    plan = ShardPlan(
        config_path=str(work_dir / "original.yaml"),
        split_by="symbol",
        shards=[
            ShardSpec(shard_id="done", config_path=str(done_config), output_path=str(done_output)),
            ShardSpec(shard_id="pending", config_path=str(pending_config), output_path=str(pending_output)),
        ],
    )
    write_shard_manifest(plan, work_dir / "manifest.json")

    metadata = BacktestListItem(
        id=backtest_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        status="running",
        total_runs=6,
        execution_backend="argo",
        workflow_name="backtest-blend-test",
    )
    workflow = {
        "status": {
            "phase": "Running",
            "progress": "35/100",
            "nodes": {
                "pending-node": {
                    "templateName": "run-shard",
                    "phase": "Running",
                    "progress": "50/100",
                    "inputs": {
                        "parameters": [
                            {"name": "shard-id", "value": "pending"},
                            {"name": "shard-output-path", "value": str(pending_output)},
                        ]
                    },
                }
            },
        }
    }

    completed_runs, fallback_pct = blend_completed_runs(metadata, tmp_path, workflow=workflow)

    assert completed_runs == 4
    assert fallback_pct == 35.0


def test_blend_completed_runs_workflow_fallback_pct(tmp_path: Path) -> None:
    metadata = BacktestListItem(
        id="fallback-test",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        status="running",
        total_runs=10,
        execution_backend="argo",
        workflow_name="backtest-fallback-test",
    )
    workflow = {"status": {"phase": "Running", "progress": "30/100", "nodes": {}}}

    completed_runs, fallback_pct = blend_completed_runs(metadata, tmp_path, workflow=workflow)

    assert completed_runs == 0
    assert fallback_pct == 30.0


def test_build_status_response_uses_fallback_pct() -> None:
    from app.backtests.service import build_status_response

    metadata = BacktestListItem(
        id="status-fallback",
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        status="running",
        total_runs=10,
        execution_backend="argo",
    )
    response = build_status_response(metadata, completed_runs=0, fallback_pct=30.0)
    assert response.progress_pct == 30.0
