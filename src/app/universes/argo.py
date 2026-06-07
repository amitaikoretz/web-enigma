from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.argo_submission_logging import log_argo_workflow_submission
from app.backtests.argo import ArgoWorkflowConfig, load_argo_workflow_config
from app.universes.argo_workflow import (
    build_symbol_universe_refresh_workflow_spec,
    build_symbol_universe_registry_sync_workflow_spec,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SymbolUniverseArgoConfig:
    namespace: str
    enabled: bool


def load_symbol_universe_argo_config() -> SymbolUniverseArgoConfig:
    namespace = os.environ.get("UNIVERSE_ARGO_NAMESPACE", os.environ.get("ARGO_NAMESPACE", "backtest-workflows"))
    enabled = os.environ.get("UNIVERSE_ARGO_ENABLED", "").lower() in {"1", "true", "yes"}
    if not enabled:
        enabled = bool(os.environ.get("ARGO_SERVER_URL", "").strip())
    return SymbolUniverseArgoConfig(namespace=namespace, enabled=enabled)


class SymbolUniverseWorkflowSubmitter:
    def __init__(
        self,
        config: SymbolUniverseArgoConfig | None = None,
        argo_config: ArgoWorkflowConfig | None = None,
    ):
        self.config = config or load_symbol_universe_argo_config()
        self.argo = argo_config or load_argo_workflow_config()
        self._http_client: httpx.Client | None = None

    @property
    def is_configured(self) -> bool:
        return self.config.enabled and self.argo.enabled and self.argo.server_url is not None

    def _http_client_instance(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                verify=not self.argo.insecure_skip_verify,
                timeout=30.0,
            )
        return self._http_client

    def _http_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.argo.token:
            headers["Authorization"] = f"Bearer {self.argo.token}"
        return headers

    def _http_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        endpoint_name = kwargs.pop("endpoint_name", None)
        if not self.argo.server_url:
            raise RuntimeError("ARGO_SERVER_URL is not configured")
        url = f"{self.argo.server_url}{path}"
        if method.upper() == "POST" and endpoint_name is not None:
            log_argo_workflow_submission(
                logger,
                endpoint_name=str(endpoint_name),
                method=method,
                path=path,
                payload=kwargs.get("json"),
            )
        return self._http_client_instance().request(method, url, headers=self._http_headers(), **kwargs)

    def submit_refresh(self, *, universe_key: str | None, as_of: str) -> tuple[str, str]:
        if not self.is_configured:
            raise RuntimeError("Argo Workflows is not configured for symbol universe refresh submission")
        workflow_name = f"universe-refresh-{uuid.uuid4().hex[:10]}"
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
                        "app.kubernetes.io/component": "symbol-universe-refresh",
                    },
                },
                "spec": build_symbol_universe_refresh_workflow_spec(universe_key=universe_key, as_of=as_of),
            },
        }
        response = self._http_request(
            "POST",
            f"/api/v1/workflows/{self.config.namespace}",
            endpoint_name="universes.argo.submit_refresh",
            json=body,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to submit Argo workflow: {response.status_code} {response.text}")
        return workflow_name, self.config.namespace

    def submit_sync_registry(self) -> tuple[str, str]:
        if not self.is_configured:
            raise RuntimeError("Argo Workflows is not configured for universe registry sync submission")
        workflow_name = f"universe-registry-sync-{uuid.uuid4().hex[:10]}"
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
                        "app.kubernetes.io/component": "symbol-universe-registry-sync",
                    },
                },
                "spec": build_symbol_universe_registry_sync_workflow_spec(),
            },
        }
        response = self._http_request(
            "POST",
            f"/api/v1/workflows/{self.config.namespace}",
            endpoint_name="universes.argo.submit_sync_registry",
            json=body,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to submit Argo workflow: {response.status_code} {response.text}")
        return workflow_name, self.config.namespace
