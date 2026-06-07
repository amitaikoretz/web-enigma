from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.argo_template import load_yaml_template, patch_yaml_template

WORKFLOW_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_WORKFLOW_RESULTS_MOUNT = "/data/backtest-results"
WORKFLOW_RETRY_LIMIT = 3
WORKFLOW_RETRY_MEMORY_TIERS = ("4Gi", "8Gi", "16Gi", "32Gi")

_TEMPLATE_PATH = Path(__file__).with_name("backtest_workflow_template.yaml")


def workflow_results_mount() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_RESULTS_MOUNT", DEFAULT_WORKFLOW_RESULTS_MOUNT).rstrip("/")


def workflow_artifact_paths(backtest_id: str) -> tuple[str, str]:
    base = workflow_results_mount()
    work_dir = f"{base}/{backtest_id}"
    return f"{work_dir}/{backtest_id}.yaml", f"{work_dir}/{backtest_id}.json"


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


def _api_base_url() -> str:
    return os.environ.get("BACKTEST_API_BASE_URL", "http://api.backtest.svc.cluster.local:8000")


def _load_template() -> dict[str, Any]:
    return load_yaml_template(_TEMPLATE_PATH)


def build_backtest_workflow_spec(
    *,
    config_path: str,
    output_path: str,
    split_by: str,
    backtest_id: str,
    config_yaml: str | None = None,
    api_base_url: str | None = None,
    shard_parallelism: int = 8,
) -> dict[str, Any]:
    template = _load_template()
    config_b64 = ""
    if config_yaml:
        import base64

        config_b64 = base64.b64encode(config_yaml.encode()).decode()
    spec = patch_yaml_template(
        template,
        {
            "__WORKFLOW_IMAGE__": _workflow_image(),
            "__SERVICE_ACCOUNT__": _workflow_service_account(),
            "__RESULTS_CLAIM__": _results_claim_name(),
            "__CACHE_CLAIM__": _cache_claim_name(),
            "__SECRET_NAME__": _secret_name(),
            "__WORKFLOW_RESULTS_MOUNT__": workflow_results_mount(),
            "__API_BASE_URL__": api_base_url or _api_base_url(),
            "__SHARD_PARALLELISM__": str(shard_parallelism),
            "__CONFIG_PATH__": config_path,
            "__OUTPUT_PATH__": output_path,
            "__SPLIT_BY__": split_by,
            "__BACKTEST_ID__": backtest_id,
            "__CONFIG_B64__": config_b64,
        },
    )
    spec["parallelism"] = shard_parallelism
    return spec
