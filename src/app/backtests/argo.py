from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ArgoWorkflowConfig:
    namespace: str
    workflow_template: str
    enabled: bool


def load_argo_workflow_config() -> ArgoWorkflowConfig:
    namespace = os.environ.get("ARGO_NAMESPACE", "backtest")
    template = os.environ.get("BACKTEST_WORKFLOW_TEMPLATE", "backtest-batch")
    enabled = os.environ.get("BACKTEST_ARGO_ENABLED", "").lower() in {"1", "true", "yes"}
    if not enabled:
        enabled = bool(os.environ.get("KUBERNETES_SERVICE_HOST"))
    return ArgoWorkflowConfig(namespace=namespace, workflow_template=template, enabled=enabled)


class ArgoWorkflowSubmitter:
    def __init__(self, config: ArgoWorkflowConfig | None = None):
        self.config = config or load_argo_workflow_config()
        self._api: Any | None = None

    @property
    def is_configured(self) -> bool:
        if not self.config.enabled:
            return False
        try:
            self._custom_objects_api()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _custom_objects_api(self) -> Any:
        if self._api is not None:
            return self._api
        from kubernetes import client, config as k8s_config
        from kubernetes.client import ApiException

        self._ApiException = ApiException
        try:
            k8s_config.load_incluster_config()
        except k8s_config.ConfigException:
            try:
                k8s_config.load_kube_config()
            except k8s_config.ConfigException as exc:
                raise RuntimeError("Kubernetes configuration not available") from exc

        self._api = client.CustomObjectsApi()
        return self._api

    def submit(
        self,
        *,
        config_path: str,
        output_path: str,
        split_by: str,
        backtest_id: str,
    ) -> tuple[str, str]:
        api = self._custom_objects_api()
        workflow_name = f"backtest-{backtest_id[:12]}-{uuid.uuid4().hex[:6]}"
        body = {
            "apiVersion": "argoproj.io/v1alpha1",
            "kind": "Workflow",
            "metadata": {
                "name": workflow_name,
                "namespace": self.config.namespace,
                "labels": {
                    "backtest-id": backtest_id,
                    "app.kubernetes.io/component": "backtest",
                },
            },
            "spec": {
                "workflowTemplateRef": {"name": self.config.workflow_template},
                "arguments": {
                    "parameters": [
                        {"name": "config-path", "value": config_path},
                        {"name": "output-path", "value": output_path},
                        {"name": "split-by", "value": split_by},
                        {"name": "backtest-id", "value": backtest_id},
                    ]
                },
            },
        }
        try:
            api.create_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.config.namespace,
                plural="workflows",
                body=body,
            )
        except self._ApiException as exc:  # type: ignore[attr-defined]
            raise RuntimeError(f"Failed to submit Argo workflow: {exc}") from exc
        return workflow_name, self.config.namespace

    def get_workflow_phase(self, workflow_name: str) -> str | None:
        api = self._custom_objects_api()
        try:
            resource = api.get_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.config.namespace,
                plural="workflows",
                name=workflow_name,
            )
        except self._ApiException:  # type: ignore[attr-defined]
            return None
        status = resource.get("status") if isinstance(resource, dict) else None
        if not isinstance(status, dict):
            return None
        phase = status.get("phase")
        return str(phase) if phase is not None else None

    def list_workflows_for_backtest(self, backtest_id: str) -> list[dict[str, Any]]:
        api = self._custom_objects_api()
        label_selector = f"backtest-id={backtest_id}"
        try:
            response = api.list_namespaced_custom_object(
                group="argoproj.io",
                version="v1alpha1",
                namespace=self.config.namespace,
                plural="workflows",
                label_selector=label_selector,
            )
        except self._ApiException:  # type: ignore[attr-defined]
            return []
        items = response.get("items") if isinstance(response, dict) else None
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]
