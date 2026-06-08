from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.argo_template import load_yaml_template, patch_yaml_template
from app.backtests.argo_workflow import WORKFLOW_TTL_SECONDS, workflow_results_mount
from app.terminal_command import format_terminal_command

_TEMPLATE_PATH = Path(__file__).with_name("risk_workflow_template.yaml")


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _results_claim_name() -> str:
    return os.environ.get("BACKTEST_RESULTS_CLAIM", "backtest-results")


def _cache_claim_name() -> str:
    return os.environ.get("BACKTEST_CACHE_CLAIM", "backtest-cache")


def _secret_name() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_SECRET", "app-secrets")


def _command_line(
    *,
    group_id: str,
    backtest_ids_json: str,
    dataset_config_json: str,
    artifact_dir: str,
) -> str:
    return format_terminal_command(
        [
            "python",
            "-m",
            "app.standalone.risk_build_dataset_argo",
            "--group-id",
            group_id,
            "--backtest-ids-json",
            backtest_ids_json,
            "--dataset-config-json",
            dataset_config_json,
            "--artifact-dir",
            artifact_dir,
        ]
    )


def build_risk_model_workflow_spec(
    *,
    group_id: str,
    family: str,
    backtest_ids_json: str,
    dataset_config_json: str,
    train_config_json: str,
    artifact_dir: str,
) -> dict[str, Any]:
    template = load_yaml_template(_TEMPLATE_PATH)
    return patch_yaml_template(
        template,
        {
            "__WORKFLOW_IMAGE__": _workflow_image(),
            "__SERVICE_ACCOUNT__": _workflow_service_account(),
            "__RESULTS_CLAIM__": _results_claim_name(),
            "__CACHE_CLAIM__": _cache_claim_name(),
            "__SECRET_NAME__": _secret_name(),
            "__WORKFLOW_RESULTS_MOUNT__": workflow_results_mount(),
            "__TTL_SECONDS__": WORKFLOW_TTL_SECONDS,
            "__COMMAND_LINE__": _command_line(
                group_id=group_id,
                backtest_ids_json=backtest_ids_json,
                dataset_config_json=dataset_config_json,
                artifact_dir=artifact_dir,
            ),
            "__GROUP_ID__": group_id,
            "__FAMILY__": family,
            "__BACKTEST_IDS_JSON__": backtest_ids_json,
            "__DATASET_CONFIG_JSON__": dataset_config_json,
            "__TRAIN_CONFIG_JSON__": train_config_json,
            "__ARTIFACT_DIR__": artifact_dir,
        },
    )
