from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.argo_submission_logging import log_argo_workflow_submission
from app.market_overview.argo_workflow import build_market_overview_workflow_spec

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketOverviewArgoConfig:
    namespace: str
    enabled: bool = True
    server_url: str | None = None
    token: str | None = None
    insecure_skip_verify: bool = False

    @property
    def uses_http(self) -> bool:
        return self.server_url is not None


def load_market_overview_argo_config() -> MarketOverviewArgoConfig:
    namespace = os.environ.get("MARKET_OVERVIEW_ARGO_NAMESPACE", os.environ.get("ARGO_NAMESPACE", "backtest-workflows"))
    server_url = os.environ.get("ARGO_SERVER_URL", "").strip() or None
    token = os.environ.get("ARGO_TOKEN", "").strip() or None
    insecure_skip_verify = os.environ.get("ARGO_SERVER_INSECURE_SKIP_VERIFY", "").lower() in {"1", "true", "yes"}
    enabled = os.environ.get("MARKET_OVERVIEW_ARGO_ENABLED", "").lower() in {"1", "true", "yes"}
    if not enabled:
        enabled = bool(server_url)
    if server_url is not None:
        server_url = server_url.rstrip("/")
    return MarketOverviewArgoConfig(
        namespace=namespace,
        enabled=enabled,
        server_url=server_url,
        token=token,
        insecure_skip_verify=insecure_skip_verify,
    )


def _phase_from_workflow_resource(resource: dict[str, Any]) -> str | None:
    workflow = resource.get("workflow")
    if isinstance(workflow, dict):
        resource = workflow
    status = resource.get("status")
    if not isinstance(status, dict):
        return None
    phase = status.get("phase")
    return str(phase) if phase is not None else None


class MarketOverviewArgoSubmitter:
    def __init__(self, config: MarketOverviewArgoConfig | None = None):
        self.config = config or load_market_overview_argo_config()
        self._http_client: httpx.Client | None = None

    @property
    def is_configured(self) -> bool:
        return self.config.enabled and self.config.server_url is not None

    def _http_client_instance(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(verify=not self.config.insecure_skip_verify, timeout=30.0)
        return self._http_client

    def _http_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    def _http_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        endpoint_name = kwargs.pop("endpoint_name", None)
        if not self.config.server_url:
            raise RuntimeError("ARGO_SERVER_URL is not configured")
        url = f"{self.config.server_url}{path}"
        if method.upper() == "POST" and endpoint_name is not None:
            log_argo_workflow_submission(
                logger,
                endpoint_name=str(endpoint_name),
                method=method,
                path=path,
                payload=kwargs.get("json"),
            )
        return self._http_client_instance().request(method, url, headers=self._http_headers(), **kwargs)

    def submit(self, *, snapshot_id: str, output_path: str, api_base_url: str | None = None) -> tuple[str, str]:
        workflow_name = f"market-overview-{snapshot_id[:12]}-{uuid.uuid4().hex[:6]}"
        body = {
            "namespace": self.config.namespace,
            "serverDryRun": False,
            "workflow": {
                "apiVersion": "argoproj.io/v1alpha1",
                "kind": "Workflow",
                "metadata": {
                    "name": workflow_name,
                    "namespace": self.config.namespace,
                    "labels": {
                        "market-overview-id": snapshot_id,
                        "app.kubernetes.io/component": "market-overview",
                    },
                },
                "spec": build_market_overview_workflow_spec(
                    snapshot_id=snapshot_id,
                    output_path=output_path,
                    api_base_url=api_base_url,
                ),
            },
        }
        response = self._http_request(
            "POST",
            f"/api/v1/workflows/{self.config.namespace}",
            endpoint_name="market_overview.argo.submit",
            json=body,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to submit Argo workflow: {response.status_code} {response.text}")
        return workflow_name, self.config.namespace

    def get_workflow(self, workflow_name: str, *, namespace: str | None = None) -> dict[str, Any] | None:
        target_namespace = namespace or self.config.namespace
        response = self._http_request("GET", f"/api/v1/workflows/{target_namespace}/{workflow_name}")
        if response.status_code == 404 or response.status_code >= 400:
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None

    def get_workflow_phase(self, workflow_name: str, *, namespace: str | None = None) -> str | None:
        workflow = self.get_workflow(workflow_name, namespace=namespace)
        if workflow is None:
            return None
        return _phase_from_workflow_resource(workflow)
