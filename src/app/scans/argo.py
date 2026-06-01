from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from app.backtests.argo import ArgoWorkflowConfig, ArgoWorkflowSubmitter, load_argo_workflow_config
from app.scans.argo_workflow import build_scan_workflow_spec
from app.scans.models import ScanType


@dataclass(frozen=True)
class ScanArgoSubmitConfig:
    namespace: str


class ScanArgoSubmitter:
    def __init__(
        self,
        *,
        config: ArgoWorkflowConfig | None = None,
        http_submitter: ArgoWorkflowSubmitter | None = None,
    ):
        self.config = config or load_argo_workflow_config()
        self.http = http_submitter or ArgoWorkflowSubmitter(self.config)

    @property
    def is_configured(self) -> bool:
        return self.http.is_configured

    def _build_workflow_resource(
        self,
        *,
        scan_type: ScanType,
        scan_id: str,
        results_path: str,
        params_json: str,
    ) -> dict[str, Any]:
        workflow_name = f"scan-{scan_type}-{scan_id[:12]}-{uuid.uuid4().hex[:6]}"
        return {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {
                "name": workflow_name,
                "namespace": self.config.namespace,
                "labels": {
                    "scan-id": scan_id,
                    "scan-type": scan_type,
                    "app.kubernetes.io/component": "scan",
                },
            },
            "spec": build_scan_workflow_spec(
                scan_type=scan_type,
                scan_id=scan_id,
                results_path=results_path,
                params_json=params_json,
            ),
        }

    def submit(
        self,
        *,
        scan_type: ScanType,
        scan_id: str,
        results_path: str,
        params_json: str,
    ) -> tuple[str, str]:
        resource = self._build_workflow_resource(
            scan_type=scan_type,
            scan_id=scan_id,
            results_path=results_path,
            params_json=params_json,
        )
        namespace = self.config.namespace
        body = {"namespace": namespace, "serverDryRun": False, "workflow": resource}
        response = self.http._http_request("POST", f"/api/v1/workflows/{namespace}", json=body)
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to submit Argo workflow: {response.status_code} {response.text}")
        return resource["metadata"]["name"], namespace

    def get_workflow_phase(self, workflow_name: str) -> str | None:
        return self.http.get_workflow_phase(workflow_name)
