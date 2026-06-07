from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.argo_template import load_yaml_template, patch_yaml_template
from app.backtests.argo_workflow import workflow_results_mount

_TEMPLATE_PATH = Path(__file__).with_name("datasets_workflow_template.yaml")


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def build_dataset_workflow_spec(
    *,
    symbol: str,
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
    workflow_template = patch_yaml_template(
        template,
        {
            "__WORKFLOW_IMAGE__": _workflow_image(),
            "__SERVICE_ACCOUNT__": _workflow_service_account(),
            "__WORKFLOW_RESULTS_MOUNT__": workflow_results_mount(),
            "__SYMBOL__": symbol,
            "__PROVIDER__": provider,
            "__RESOLUTION__": resolution,
            "__START_DATE__": start_date,
            "__END_DATE__": end_date,
            "__OPTIONS_ENABLED__": "true" if options_enabled else "false",
            "__OPTIONS_FEED__": options_feed,
            "__OUTPUT_DIR__": output_dir,
            "__OPTIONS_ENABLED_FLAG__": options_enabled_flag,
        },
    )
    spec = workflow_template.get("spec")
    if not isinstance(spec, dict):
        raise ValueError("dataset workflow template must contain a spec mapping")
    return spec
