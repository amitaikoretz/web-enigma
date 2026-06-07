from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.backtests.argo import ArgoWorkflowSubmitter
from app.daily_index_forecast.argo_workflow import build_daily_index_forecast_workflow_spec


@dataclass(frozen=True)
class DailyIndexForecastArgoSubmitter:
    submitter: ArgoWorkflowSubmitter
    workflow_prefix: str = "daily-index-forecast"
    component_label: str = "daily-index-forecast"

    def submit(
        self,
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
        family: str = "daily_index_forecast",
    ) -> tuple[str, str]:
        workflow_name = f"{self.workflow_prefix}-{group_id[:12]}-{uuid.uuid4().hex[:6]}"
        body = {
            "namespace": self.submitter.config.namespace,
            "serverDryRun": False,
            "workflow": {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Workflow",
                "metadata": {
                    "name": workflow_name,
                    "namespace": self.submitter.config.namespace,
                    "labels": {
                        f"{self.component_label}-group-id": group_id,
                        f"{self.component_label}-feature-run-id": feature_run_id,
                        "app.kubernetes.io/component": self.component_label,
                    },
                },
                "spec": build_daily_index_forecast_workflow_spec(
                    group_id=group_id,
                    feature_run_id=feature_run_id,
                    universe_json=universe_json,
                    feature_config_json=feature_config_json,
                    walk_forward_json=walk_forward_json,
                    train_config_json=train_config_json,
                    costs_json=costs_json,
                    data_cache_json=data_cache_json,
                    artifact_dir=artifact_dir,
                    feature_artifact_dir=feature_artifact_dir,
                    family=family,
                ),
            },
        }
        response = self.submitter._http_request(
            "POST",
            f"/api/v1/workflows/{self.submitter.config.namespace}",
            json=body,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to submit Argo workflow: {response.status_code} {response.text}")
        return workflow_name, self.submitter.config.namespace

