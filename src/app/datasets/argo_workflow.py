from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.argo_template import load_yaml_template, patch_yaml_template
from app.backtests.argo_workflow import workflow_results_mount
from app.terminal_command import format_terminal_command

_TEMPLATE_PATH = Path(__file__).with_name("datasets_workflow_template.yaml")
_RETRY_LIMIT = 3
_RETRY_BACKOFF = {"duration": "10s", "factor": 2, "maxDuration": "1m"}
_RETRY_MEMORY_TIERS = ("1Gi", "2Gi", "4Gi", "8Gi")
_DEFAULT_MAX_PODS = 4


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _dataset_max_pods() -> int:
    raw = os.environ.get("DATASET_MAX_PODS", str(_DEFAULT_MAX_PODS)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MAX_PODS


def _dataset_retry_strategy() -> dict[str, Any]:
    return {
        "limit": _RETRY_LIMIT,
        "retryPolicy": "Always",
        "backoff": _RETRY_BACKOFF,
    }


def _dataset_retry_memory_expression() -> str:
    tiers = list(_RETRY_MEMORY_TIERS)
    if not tiers:
        raise ValueError("dataset retry memory tiers must not be empty")

    expression = f'"{tiers[-1]}"'
    for retry_index in range(len(tiers) - 2, -1, -1):
        tier = tiers[retry_index]
        condition = f"asInt(retries) == {retry_index}"
        expression = f'{condition} ? "{tier}" : {expression}'
    return f"{{{{={expression}}}}}"


def _dataset_pod_spec_patch() -> str:
    memory_expression = _dataset_retry_memory_expression()
    return (
        "containers:\n"
        "  - name: main\n"
        "    resources:\n"
        "      requests:\n"
        f"        memory: {memory_expression}\n"
        "      limits:\n"
        f"        memory: {memory_expression}\n"
    )


def _apply_dataset_retry_strategy(spec: dict[str, Any]) -> None:
    templates = spec.get("templates")
    if not isinstance(templates, list):
        raise ValueError("dataset workflow template must contain a templates list")
    retryable_templates = {"print-payload", "plan-shards", "aggregate-progress", "download-shard", "combine-shards"}
    for template in templates:
        if not isinstance(template, dict):
            continue
        if template.get("name") not in retryable_templates:
            continue
        template["retryStrategy"] = _dataset_retry_strategy()
        template["podSpecPatch"] = _dataset_pod_spec_patch()


def _command_line(
    *,
    symbols: list[str],
    provider: str,
    resolution: str,
    start_date: str,
    end_date: str,
    options_enabled_flag: str,
    options_feed: str,
    output_dir: str,
) -> str:
    return format_terminal_command(
        [
            "python",
            "-m",
            "app.standalone.datasets_download_argo",
            "--symbol",
            ",".join(symbols),
            "--provider",
            provider,
            "--resolution",
            resolution,
            "--start-date",
            start_date,
            "--end-date",
            end_date,
            options_enabled_flag,
            "--options-feed",
            options_feed,
            "--output-dir",
            output_dir,
        ]
    )


def build_dataset_workflow_spec(
    *,
    symbols: list[str],
    provider: str,
    resolution: str,
    start_date: str,
    end_date: str,
    options_enabled: bool,
    options_feed: str,
    output_dir: str,
    options_enabled_flag: str,
) -> dict[str, Any]:
    template = load_yaml_template(_TEMPLATE_PATH)
    command_line = _command_line(
        symbols=symbols,
        provider=provider,
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        options_enabled_flag=options_enabled_flag,
        options_feed=options_feed,
        output_dir=output_dir,
    )
    workflow_template = patch_yaml_template(
        template,
        {
            "__WORKFLOW_IMAGE__": _workflow_image(),
            "__SERVICE_ACCOUNT__": _workflow_service_account(),
            "__WORKFLOW_RESULTS_MOUNT__": workflow_results_mount(),
            "__COMMAND_LINE__": command_line,
            "__SYMBOLS__": ",".join(symbols),
            "__PROVIDER__": provider,
            "__RESOLUTION__": resolution,
            "__START_DATE__": start_date,
            "__END_DATE__": end_date,
            "__OPTIONS_ENABLED__": "true" if options_enabled else "false",
            "__OPTIONS_FEED__": options_feed,
            "__OUTPUT_DIR__": output_dir,
            "__OPTIONS_ENABLED_FLAG__": options_enabled_flag,
            "__MAX_PODS__": str(_dataset_max_pods()),
        },
    )
    spec = workflow_template.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("dataset workflow template must contain a spec mapping")
    _apply_dataset_retry_strategy(spec)
    return spec
