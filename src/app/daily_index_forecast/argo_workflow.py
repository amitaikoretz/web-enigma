from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.argo_template import load_yaml_template, patch_yaml_template
from app.backtests.argo_workflow import workflow_results_mount

_TEMPLATE_PATH = Path(__file__).with_name("daily_index_workflow_template.yaml")


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _secret_name() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_SECRET", "app-secrets")


def build_daily_index_forecast_workflow_spec(
    *,
    group_id: str,
    feature_run_id: str,
    universe_json: str,
    feature_config_json: str,
    walk_forward_json: str,
    train_config_json: str,
    costs_json: str,
    data_cache_json: str,
    artifact_dir: str,
    feature_artifact_dir: str,
    family: str,
) -> dict[str, Any]:
    template = load_yaml_template(_TEMPLATE_PATH)
    return patch_yaml_template(
        template,
        {
            "__WORKFLOW_IMAGE__": _workflow_image(),
            "__SERVICE_ACCOUNT__": _workflow_service_account(),
            "__SECRET_NAME__": _secret_name(),
            "__WORKFLOW_RESULTS_MOUNT__": workflow_results_mount(),
            "__GROUP_ID__": group_id,
            "__FEATURE_RUN_ID__": feature_run_id,
            "__UNIVERSE_JSON__": universe_json,
            "__FEATURE_CONFIG_JSON__": feature_config_json,
            "__WALK_FORWARD_JSON__": walk_forward_json,
            "__TRAIN_CONFIG_JSON__": train_config_json,
            "__COSTS_JSON__": costs_json,
            "__DATA_CACHE_JSON__": data_cache_json,
            "__ARTIFACT_DIR__": artifact_dir,
            "__FEATURE_ARTIFACT_DIR__": feature_artifact_dir,
            "__FAMILY__": family,
        },
    )
