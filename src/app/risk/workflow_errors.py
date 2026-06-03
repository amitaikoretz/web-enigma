from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


_FAILED_PHASES = {"Failed", "Error"}
_ERROR_OUTPUT_NAMES = {
    "error-exception",
    "error-code-location",
    "error-call-stack",
    "error-traceback",
}


@dataclass(frozen=True)
class WorkflowErrorDetails:
    available: bool
    status_message: str | None
    argo_phase: str | None
    failed_node_name: str | None
    failed_template_name: str | None
    error_exception: str | None
    error_code_location: str | None
    error_call_stack: list[str]
    error_traceback: str | None


def _workflow_status(workflow: dict[str, Any]) -> dict[str, Any]:
    status = workflow.get("status")
    return status if isinstance(status, dict) else {}


def workflow_phase(workflow: dict[str, Any]) -> str | None:
    phase = _workflow_status(workflow).get("phase")
    return str(phase) if phase is not None else None


def workflow_nodes(workflow: dict[str, Any]) -> dict[str, Any]:
    nodes = _workflow_status(workflow).get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _node_children(node: dict[str, Any]) -> set[str]:
    children = node.get("children")
    if not isinstance(children, list):
        return set()
    return {str(child) for child in children if child is not None}


def _node_outputs(node: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = node.get("outputs")
    if not isinstance(outputs, dict):
        return []
    parameters = outputs.get("parameters")
    if not isinstance(parameters, list):
        return []
    return [item for item in parameters if isinstance(item, dict)]


def _node_output_value(node: dict[str, Any], name: str) -> str | None:
    for item in _node_outputs(node):
        if item.get("name") != name:
            continue
        value = item.get("value")
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    return None


def _node_has_error_outputs(node: dict[str, Any]) -> bool:
    return any(_node_output_value(node, name) for name in _ERROR_OUTPUT_NAMES)


def _node_sort_key(node_id: str, node: dict[str, Any]) -> tuple[float, float, str, str]:
    def _parse(value: Any) -> float:
        if not isinstance(value, str) or not value.strip():
            return 0.0
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            else:
                parsed = parsed.astimezone(UTC)
            return parsed.timestamp()
        except ValueError:
            return 0.0

    finished_at = _parse(node.get("finishedAt"))
    started_at = _parse(node.get("startedAt"))
    display_name = str(node.get("displayName") or node.get("name") or "")
    return finished_at, started_at, display_name, node_id


def _pick_failed_node(nodes: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    failed_nodes: list[tuple[str, dict[str, Any]]] = []
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        if str(node.get("phase") or "") not in _FAILED_PHASES:
            continue
        failed_nodes.append((str(node_id), node))

    if not failed_nodes:
        return None

    leaf_failed_nodes = [
        (node_id, node)
        for node_id, node in failed_nodes
        if not _node_children(node) or not any(child_id in nodes for child_id in _node_children(node))
    ]
    candidates = leaf_failed_nodes or failed_nodes
    candidates_with_outputs = [
        (node_id, node) for node_id, node in candidates if _node_has_error_outputs(node)
    ]
    ranked_candidates = candidates_with_outputs or candidates
    return max(ranked_candidates, key=lambda item: _node_sort_key(item[0], item[1]))


def extract_workflow_error_details(workflow: dict[str, Any] | None) -> WorkflowErrorDetails:
    if workflow is None:
        return WorkflowErrorDetails(
            available=False,
            status_message="Workflow not found in Argo.",
            argo_phase=None,
            failed_node_name=None,
            failed_template_name=None,
            error_exception=None,
            error_code_location=None,
            error_call_stack=[],
            error_traceback=None,
        )

    phase = workflow_phase(workflow)
    nodes = workflow_nodes(workflow)
    picked = _pick_failed_node(nodes)
    if picked is None:
        return WorkflowErrorDetails(
            available=False,
            status_message="No failed workflow step with error outputs was found.",
            argo_phase=phase,
            failed_node_name=None,
            failed_template_name=None,
            error_exception=None,
            error_code_location=None,
            error_call_stack=[],
            error_traceback=None,
        )

    node_id, node = picked
    error_exception = _node_output_value(node, "error-exception")
    error_code_location = _node_output_value(node, "error-code-location")
    error_traceback = _node_output_value(node, "error-traceback")
    call_stack_raw = _node_output_value(node, "error-call-stack") or ""
    error_call_stack = [line.strip() for line in call_stack_raw.splitlines() if line.strip()]
    has_any_error_output = any(
        [error_exception, error_code_location, error_call_stack, error_traceback]
    )
    if not has_any_error_output:
        return WorkflowErrorDetails(
            available=False,
            status_message="The failed workflow step did not expose any error outputs.",
            argo_phase=phase,
            failed_node_name=str(node.get("displayName") or node.get("name") or node_id),
            failed_template_name=str(node.get("templateName") or "") or None,
            error_exception=None,
            error_code_location=None,
            error_call_stack=[],
            error_traceback=None,
        )

    return WorkflowErrorDetails(
        available=True,
        status_message="Loaded error details from the failed workflow step.",
        argo_phase=phase,
        failed_node_name=str(node.get("displayName") or node.get("name") or node_id),
        failed_template_name=str(node.get("templateName") or "") or None,
        error_exception=error_exception,
        error_code_location=error_code_location,
        error_call_stack=error_call_stack,
        error_traceback=error_traceback,
    )
