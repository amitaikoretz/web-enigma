from __future__ import annotations

from pathlib import Path
from typing import Any

from app.backtests.argo_progress import parse_argo_progress, progress_fraction
from app.datasets.models import DatasetListItem
from app.datasets.sharding import DatasetShardPlan


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


def _plan_path_for_item(item: DatasetListItem) -> Path:
    return Path(item.output_dir).resolve() / item.id / "shard-plan.json"


def _load_plan(item: DatasetListItem) -> DatasetShardPlan | None:
    plan_path = _plan_path_for_item(item)
    if not plan_path.exists():
        return None
    try:
        return DatasetShardPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _weighted_progress_for_nodes(plan: DatasetShardPlan, nodes: dict[str, Any]) -> float:
    by_output_path: dict[str, dict[str, Any]] = {}
    by_shard_id: dict[str, dict[str, Any]] = {}
    combine_node: dict[str, Any] | None = None
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        template_name = node.get("templateName")
        parameters = _node_input_parameters(node)
        if template_name == "download-shard":
            shard_id = parameters.get("shard-id")
            if shard_id:
                by_shard_id[shard_id] = node
            output_dir = parameters.get("output-dir")
            if output_dir:
                by_output_path[output_dir] = node
        elif template_name == "combine-shards":
            combine_node = node

    completed = 0.0
    total = 0.0
    for shard in plan.shards:
        weight = float(shard.work_units)
        total += weight
        node = by_shard_id.get(shard.shard_id)
        if node is None:
            node = by_output_path.get(shard.output_dir)
        if node is None:
            continue
        phase = str(node.get("phase", ""))
        if phase == "Succeeded":
            completed += weight
            continue
        progress = node.get("progress")
        parsed = parse_argo_progress(str(progress)) if progress is not None else None
        if parsed is None:
            continue
        n, m = parsed
        completed += progress_fraction(n, m) * weight

    combine_weight = float(max(1, plan.combine_weight_units))
    total += combine_weight
    if combine_node is not None:
        phase = str(combine_node.get("phase", ""))
        if phase == "Succeeded":
            completed += combine_weight
        else:
            progress = combine_node.get("progress")
            parsed = parse_argo_progress(str(progress)) if progress is not None else None
            if parsed is not None:
                n, m = parsed
                completed += progress_fraction(n, m) * combine_weight

    if total <= 0:
        return 0.0
    return min(100.0, (completed / total) * 100.0)


def compute_dataset_progress_pct(
    item: DatasetListItem,
    workflow: dict[str, Any] | None,
) -> float | None:
    if workflow is None:
        return None
    plan = _load_plan(item)
    if plan is None:
        return _workflow_progress_pct(workflow)
    nodes = _workflow_nodes(workflow)
    if not nodes:
        return _workflow_progress_pct(workflow)
    weighted = _weighted_progress_for_nodes(plan, nodes)
    if weighted > 0:
        return weighted
    return _workflow_progress_pct(workflow)

