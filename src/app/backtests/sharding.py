from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from app.config.models import BacktestConfig, BacktestRunConfig, StrategyConfig

SplitBy = Literal["run", "symbol", "strategy", "symbol_strategy"]


class ShardSpec(BaseModel):
    shard_id: str
    config_path: str
    output_path: str


class ShardPlan(BaseModel):
    config_path: str
    split_by: SplitBy
    shards: list[ShardSpec] = Field(default_factory=list)


def _run_to_dict(run: BacktestRunConfig) -> dict[str, Any]:
    return run.model_dump(mode="json", exclude_none=True)


def _symbol_from_run(run: BacktestRunConfig) -> str:
    data = run.data
    if hasattr(data, "symbol"):
        return str(data.symbol).upper()
    return "unknown"


def _expand_run_to_atomic_runs(run: BacktestRunConfig) -> list[BacktestRunConfig]:
    if run.strategies:
        expanded: list[BacktestRunConfig] = []
        for entry in run.strategies:
            expanded.append(
                run.model_copy(
                    update={
                        "strategy": entry.name,
                        "strategy_params": entry.params,
                        "strategies": None,
                        "run_id": f"{run.run_id}:{entry.name}",
                    }
                )
            )
        return expanded
    return [run]


def _sanitize_shard_id(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip().lower())
    return normalized or "shard"


def _group_key_for_run(run: BacktestRunConfig, split_by: SplitBy) -> str:
    if split_by == "run":
        return run.run_id
    if split_by == "symbol":
        return _symbol_from_run(run)
    if split_by == "strategy":
        assert run.strategy is not None
        return run.strategy
    symbol = _symbol_from_run(run)
    assert run.strategy is not None
    return f"{symbol}:{run.strategy}"


def _collect_runs_by_split(config: BacktestConfig, split_by: SplitBy) -> dict[str, list[BacktestRunConfig]]:
    if split_by == "run":
        return {run.run_id: [run] for run in config.runs}

    atomic_runs: list[BacktestRunConfig] = []
    for run in config.runs:
        atomic_runs.extend(_expand_run_to_atomic_runs(run))

    grouped: dict[str, list[BacktestRunConfig]] = {}
    for run in atomic_runs:
        key = _group_key_for_run(run, split_by)
        grouped.setdefault(key, []).append(run)
    return grouped


def resolve_split_by(
    config_raw: dict[str, Any],
    *,
    override: SplitBy | None = None,
    platform_default: SplitBy = "symbol_strategy",
) -> SplitBy:
    if override is not None and override != "":
        return override
    workflow = config_raw.get("workflow")
    if isinstance(workflow, dict):
        split_by = workflow.get("split_by")
        if split_by in {"run", "symbol", "strategy", "symbol_strategy"}:
            return split_by  # type: ignore[return-value]
    return platform_default


def plan_shards(
    config_raw: dict[str, Any],
    *,
    split_by: SplitBy,
    work_dir: Path,
    config_path: str | None = None,
) -> ShardPlan:
    config = BacktestConfig.model_validate(config_raw)
    resolved_config_path = str(config_path or work_dir / "original.yaml")
    shards_dir = work_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    grouped = _collect_runs_by_split(config, split_by)
    global_config = config.global_config.model_dump(mode="json")
    shards: list[ShardSpec] = []

    for group_key, runs in sorted(grouped.items()):
        shard_id = _sanitize_shard_id(group_key)
        shard_config_path = shards_dir / f"{shard_id}.yaml"
        shard_output_path = shards_dir / f"{shard_id}.json"
        shard_raw = {
            "global_config": deepcopy(global_config),
            "runs": [_run_to_dict(run) for run in runs],
        }
        shard_config_path.write_text(
            yaml.safe_dump(shard_raw, default_flow_style=False, sort_keys=False),
            encoding="utf-8",
        )
        shards.append(
            ShardSpec(
                shard_id=shard_id,
                config_path=str(shard_config_path.resolve()),
                output_path=str(shard_output_path.resolve()),
            )
        )

    return ShardPlan(
        config_path=resolved_config_path,
        split_by=split_by,
        shards=shards,
    )


def write_shard_manifest(plan: ShardPlan, manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")


def write_shards_param(plan: ShardPlan, param_path: Path) -> None:
    param_path.parent.mkdir(parents=True, exist_ok=True)
    param_path.write_text(shards_param_json(plan), encoding="utf-8")


def load_shard_manifest(manifest_path: Path) -> ShardPlan:
    return ShardPlan.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def shards_param_json(plan: ShardPlan) -> str:
    """Compact JSON array for Argo withParam."""
    return json.dumps([shard.model_dump() for shard in plan.shards])
