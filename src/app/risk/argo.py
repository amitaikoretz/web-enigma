from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from app.backtests.argo import ArgoWorkflowSubmitter
from app.risk.argo_workflow import build_risk_model_workflow_spec


@dataclass(frozen=True)
class RiskModelArgoSubmitter:
    submitter: ArgoWorkflowSubmitter

    def submit(
        self,
        *,
        group_id: str,
        backtest_ids: list[str],
        dataset_config: dict[str, Any],
        train_config: dict[str, Any],
        artifact_dir: str,
    ) -> tuple[str, str]:
        workflow_name = f"risk-model-{group_id[:12]}-{uuid.uuid4().hex[:6]}"
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
                        "risk-model-group-id": group_id,
                        "app.kubernetes.io/component": "risk-model",
                    },
                },
                "spec": build_risk_model_workflow_spec(
                    group_id=group_id,
                    backtest_ids_json=json.dumps(backtest_ids),
                    dataset_config_json=json.dumps(dataset_config or {}),
                    train_config_json=json.dumps(train_config or {}),
                    artifact_dir=artifact_dir,
                ),
            },
        }
        response = self.submitter._http_request(  # reuse authenticated request machinery
            "POST",
            f"/api/v1/workflows/{self.submitter.config.namespace}",
            json=body,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to submit Argo workflow: {response.status_code} {response.text}")
        return workflow_name, self.submitter.config.namespace

