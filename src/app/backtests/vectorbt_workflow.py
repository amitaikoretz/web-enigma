from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.argo_template import load_yaml_template, patch_yaml_template
from app.backtests.argo_workflow import workflow_results_mount
from app.terminal_command import format_terminal_command

_TEMPLATE_PATH = Path(__file__).with_name("vectorbt_workflow_template.yaml")
_RETRY_LIMIT = 3
_RETRY_BACKOFF = {"duration": "10s", "factor": 2, "maxDuration": "2m"}
_RETRY_MEMORY_TIERS = ("1Gi", "2Gi", "4Gi", "8Gi")


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _secret_name() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_SECRET", "app-secrets")


def vectorbt_artifact_dir(backtest_id: str) -> str:
    return f"{workflow_results_mount()}/{backtest_id}"


def _retry_strategy() -> dict[str, Any]:
    return {"limit": _RETRY_LIMIT, "retryPolicy": "Always", "backoff": _RETRY_BACKOFF}


def _retry_memory_expression() -> str:
    tiers = list(_RETRY_MEMORY_TIERS)
    expression = f'"{tiers[-1]}"'
    for retry_index in range(len(tiers) - 2, -1, -1):
        expression = f'asInt(retries) == {retry_index} ? "{tiers[retry_index]}" : {expression}'
    return f"{{{{={expression}}}}}"


def _pod_spec_patch() -> str:
    memory_expression = _retry_memory_expression()
    return (
        "containers:\n"
        "  - name: main\n"
        "    resources:\n"
        "      requests:\n"
        f"        memory: {memory_expression}\n"
        "      limits:\n"
        f"        memory: {memory_expression}\n"
    )


def _apply_retry_strategy(spec: dict[str, Any]) -> None:
    templates = spec.get("templates")
    if not isinstance(templates, list):
        raise ValueError("vectorbt workflow template must contain a templates list")
    retryable_templates = {"print-payload", "run-vectorbt"}
    for template in templates:
        if not isinstance(template, dict) or template.get("name") not in retryable_templates:
            continue
        template["retryStrategy"] = _retry_strategy()
        template["podSpecPatch"] = _pod_spec_patch()


def _command_line(backtest_id: str, request_json_b64: str) -> str:
    return format_terminal_command(
        [
            "python",
            "-m",
            "app.standalone.run_vectorbt_backtest_argo",
            "--backtest-id",
            backtest_id,
            "--request-json-b64",
            request_json_b64,
            "--artifact-dir",
            vectorbt_artifact_dir(backtest_id),
        ]
    )


def build_vectorbt_workflow_spec(*, backtest_id: str, request_json_b64: str) -> dict[str, Any]:
    template = load_yaml_template(_TEMPLATE_PATH)
    workflow_template = patch_yaml_template(
        template,
        {
            "__WORKFLOW_IMAGE__": _workflow_image(),
            "__SERVICE_ACCOUNT__": _workflow_service_account(),
            "__SECRET_NAME__": _secret_name(),
            "__WORKFLOW_RESULTS_MOUNT__": workflow_results_mount(),
            "__BACKTEST_ID__": backtest_id,
            "__REQUEST_JSON_B64__": request_json_b64,
            "__ARTIFACT_DIR__": vectorbt_artifact_dir(backtest_id),
            "__COMMAND_LINE__": _command_line(backtest_id, request_json_b64),
        },
    )
    spec = workflow_template.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("vectorbt workflow template must contain a spec mapping")
    _apply_retry_strategy(spec)
    return spec
