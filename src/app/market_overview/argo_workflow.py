from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.argo_template import load_yaml_template, patch_yaml_template

WORKFLOW_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_WORKFLOW_RESULTS_MOUNT = "/data/market-overview-results"
_TEMPLATE_PATH = Path(__file__).with_name("market_overview_workflow_template.yaml")


def workflow_results_mount() -> str:
    return os.environ.get("MARKET_OVERVIEW_WORKFLOW_RESULTS_MOUNT", DEFAULT_WORKFLOW_RESULTS_MOUNT).rstrip("/")


def workflow_artifact_paths(snapshot_id: str) -> tuple[str, str]:
    base = workflow_results_mount()
    work_dir = f"{base}/{snapshot_id}"
    return f"{work_dir}/{snapshot_id}.yaml", f"{work_dir}/{snapshot_id}.json"


def _workflow_image() -> str:
    return os.environ.get("MARKET_OVERVIEW_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _results_claim_name() -> str:
    return os.environ.get("MARKET_OVERVIEW_RESULTS_CLAIM", "market-overview-results")


def _secret_name() -> str:
    return os.environ.get("MARKET_OVERVIEW_WORKFLOW_SECRET", "app-secrets")


def _api_base_url() -> str:
    return os.environ.get("MARKET_OVERVIEW_API_BASE_URL", "http://api.backtest.svc.cluster.local:8000")


def _load_template() -> dict[str, Any]:
    return load_yaml_template(_TEMPLATE_PATH)


def build_market_overview_workflow_spec(
    *,
    snapshot_id: str,
    output_path: str,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    template = _load_template()
    return patch_yaml_template(
        template,
        {
            "__WORKFLOW_IMAGE__": _workflow_image(),
            "__SERVICE_ACCOUNT__": _workflow_service_account(),
            "__RESULTS_CLAIM__": _results_claim_name(),
            "__SECRET_NAME__": _secret_name(),
            "__WORKFLOW_RESULTS_MOUNT__": workflow_results_mount(),
            "__API_BASE_URL__": api_base_url or _api_base_url(),
            "__SNAPSHOT_ID__": snapshot_id,
            "__OUTPUT_PATH__": output_path,
        },
    )
