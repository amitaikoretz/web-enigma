from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from app.backtests.argo_progress import parse_argo_progress, progress_fraction
from app.backtests.models import BacktestListItem
from app.backtests.sharding import ShardPlan, load_shard_manifest
from app.config.models import BacktestConfig
from app.output.models import BacktestReport


def count_runs_in_shard_config(config_path: Path) -> int:
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
        if not isinstance(raw, dict):
            return 0
        config = BacktestConfig.model_validate(raw)
    except (OSError, ValueError, ValidationError):
        return 0
    return len(config.runs)


def _node_input_parameters(node: dict[str, Any]) -> dict[str, str]:
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        return {}
    parameters = inputs.get("parameters")
    if not isinstance(parameters, list):
        return {}
    resolved: dict[str, str] = {}
    for item in parameters:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        if isinstance(name, str) and value is not None:
            resolved[name] = str(value)
    return resolved


def index_run_shard_nodes(nodes: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_output_path: dict[str, dict[str, Any]] = {}
    by_shard_id: dict[str, dict[str, Any]] = {}
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        if node.get("templateName") != "run-shard":
            continue
        parameters = _node_input_parameters(node)
        output_path = parameters.get("shard-output-path")
        shard_id = parameters.get("shard-id")
        if output_path:
            by_output_path[output_path] = node
        if shard_id:
            by_shard_id[shard_id] = node
    return by_output_path, by_shard_id


def _workflow_status(workflow: dict[str, Any]) -> dict[str, Any]:
    status = workflow.get("status")
    return status if isinstance(status, dict) else {}


def _workflow_nodes(workflow: dict[str, Any]) -> dict[str, Any]:
    nodes = _workflow_status(workflow).get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _workflow_progress_pct(workflow: dict[str, Any]) -> float | None:
    progress = _workflow_status(workflow).get("progress")
    if not isinstance(progress, str):
        return None
    parsed = parse_argo_progress(progress)
    if parsed is None:
        return None
    completed, total = parsed
    return progress_fraction(completed, total) * 100.0


def compute_argo_weighted_completed_runs(
    plan: ShardPlan,
    nodes: dict[str, Any],
) -> float:
    by_output_path, by_shard_id = index_run_shard_nodes(nodes)
    completed = 0.0
    for shard in plan.shards:
        if Path(shard.output_path).exists():
            continue
        node = by_output_path.get(shard.output_path) or by_shard_id.get(shard.shard_id)
        if node is None:
            continue
        runs_in_shard = count_runs_in_shard_config(Path(shard.config_path))
        if runs_in_shard <= 0:
            continue
        phase = str(node.get("phase", ""))
        if phase == "Succeeded":
            completed += runs_in_shard
            continue
        progress = node.get("progress")
        parsed = parse_argo_progress(str(progress)) if progress is not None else None
        if parsed is None:
            continue
        n, m = parsed
        completed += progress_fraction(n, m) * runs_in_shard
    return completed


def _compute_completed_runs_from_files(
    metadata: BacktestListItem,
    output_dir: Path,
    plan: ShardPlan,
) -> int:
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


def compute_completed_runs_from_argo(
    metadata: BacktestListItem,
    output_dir: Path,
    workflow: dict[str, Any],
) -> tuple[float, float | None]:
    manifest_path = output_dir / metadata.id / "manifest.json"
    if not manifest_path.exists():
        return 0.0, _workflow_progress_pct(workflow)

    plan = load_shard_manifest(manifest_path)
    nodes = _workflow_nodes(workflow)
    if not nodes:
        file_based = _compute_completed_runs_from_files(metadata, output_dir, plan)
        fallback_pct = _workflow_progress_pct(workflow)
        return float(file_based), fallback_pct

    file_based = _compute_completed_runs_from_files(metadata, output_dir, plan)
    in_flight = compute_argo_weighted_completed_runs(plan, nodes)
    return min(float(metadata.total_runs), float(file_based) + in_flight), None


def blend_completed_runs(
    metadata: BacktestListItem,
    output_dir: Path,
    *,
    workflow: dict[str, Any] | None = None,
) -> tuple[int, float | None]:
    if metadata.status in {"completed", "failed"}:
        return metadata.completed_runs, None
    if metadata.execution_backend != "argo":
        return metadata.completed_runs, None

    workflow_pct = _workflow_progress_pct(workflow) if workflow is not None else None
    manifest_path = output_dir / metadata.id / "manifest.json"
    if not manifest_path.exists():
        if workflow is None:
            return metadata.completed_runs, None
        return metadata.completed_runs, workflow_pct

    plan = load_shard_manifest(manifest_path)
    file_based = _compute_completed_runs_from_files(metadata, output_dir, plan)
    if workflow is None:
        return file_based, None

    argo_total, fallback_pct = compute_completed_runs_from_argo(metadata, output_dir, workflow)
    combined = min(metadata.total_runs, round(argo_total))
    # Prefer using Argo's workflow progress meter for UI progress, even when we can infer
    # shard-level progress for completed run counts.
    return combined, workflow_pct if workflow_pct is not None else fallback_pct
