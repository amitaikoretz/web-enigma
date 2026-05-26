from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from app.backtests.argo_workflow import build_backtest_workflow_spec


@dataclass(frozen=True)
class ArgoWorkflowConfig:
    namespace: str
    enabled: bool = True
    server_url: str | None = None
    token: str | None = None
    insecure_skip_verify: bool = False

    @property
    def uses_http(self) -> bool:
        return self.server_url is not None


def load_argo_workflow_config() -> ArgoWorkflowConfig:
    namespace = os.environ.get("ARGO_NAMESPACE", "backtest-workflows")
    server_url = os.environ.get("ARGO_SERVER_URL", "").strip() or None
    token = os.environ.get("ARGO_TOKEN", "").strip() or None
    insecure_skip_verify = os.environ.get("ARGO_SERVER_INSECURE_SKIP_VERIFY", "").lower() in {
        "1",
        "true",
        "yes",
    }
    enabled = os.environ.get("BACKTEST_ARGO_ENABLED", "").lower() in {"1", "true", "yes"}
    if not enabled:
        enabled = bool(server_url) or bool(os.environ.get("KUBERNETES_SERVICE_HOST"))
    if server_url is not None:
        server_url = server_url.rstrip("/")
    return ArgoWorkflowConfig(
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


class ArgoWorkflowSubmitter:
    def __init__(self, config: ArgoWorkflowConfig | None = None):
        self.config = config or load_argo_workflow_config()
        self._api: Any | None = None
        self._http_client: httpx.Client | None = None

    @property
    def is_configured(self) -> bool:
        if not self.config.enabled:
            return False
        if self.config.uses_http:
            return True
        try:
            self._custom_objects_api()
            return True
        except Exception:  # noqa: BLE001
            return False

    def _build_workflow_resource(
        self,
        *,
        workflow_name: str,
        config_path: str,
        output_path: str,
        split_by: str,
        backtest_id: str,
        config_yaml: str | None = None,
    ) -> dict[str, Any]:
        return {
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
            "spec": build_backtest_workflow_spec(
                config_path=config_path,
                output_path=output_path,
                split_by=split_by,
                backtest_id=backtest_id,
                config_yaml=config_yaml,
            ),
        }

    def _http_client_instance(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(
                verify=not self.config.insecure_skip_verify,
                timeout=30.0,
            )
        return self._http_client

    def _http_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        return headers

    def _http_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        if not self.config.server_url:
            raise RuntimeError("Argo server URL is not configured")
        url = f"{self.config.server_url}{path}"
        try:
            return self._http_client_instance().request(method, url, headers=self._http_headers(), **kwargs)
        except httpx.ConnectError as exc:
            raise self._connect_error(url, exc) from exc

    def _connect_error(self, url: str, exc: httpx.ConnectError) -> RuntimeError:
        error_text = str(exc)
        if exc.__cause__ is not None:
            error_text = f"{error_text} {exc.__cause__}"
        if "WRONG_VERSION_NUMBER" in error_text:
            if self.config.server_url and self.config.server_url.startswith("https://"):
                http_url = "http://" + self.config.server_url.removeprefix("https://")
                return RuntimeError(
                    "Failed to connect to Argo server: TLS handshake failed because the server "
                    f"is speaking plain HTTP, not HTTPS. Set ARGO_SERVER_URL to {http_url!r} "
                    "(or enable TLS on the Argo server)."
                )
            return RuntimeError(
                "Failed to connect to Argo server: TLS handshake failed because the server "
                "is speaking plain HTTP, not HTTPS. Use an http:// URL in ARGO_SERVER_URL."
            )
        return RuntimeError(f"Failed to connect to Argo server at {url}: {exc}")

    def _ensure_kubernetes_bearer_token(self) -> None:
        from kubernetes import client

        if not os.environ.get("KUBERNETES_SERVICE_HOST"):
            return
        token_path = "/var/run/secrets/kubernetes.io/serviceaccount/token"
        ca_path = "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        if not os.path.exists(token_path):
            return
        host = os.environ["KUBERNETES_SERVICE_HOST"]
        port = os.environ.get("KUBERNETES_SERVICE_PORT_HTTPS", "443")
        with open(token_path, encoding="utf-8") as handle:
            token = handle.read().strip()
        configuration = client.Configuration.get_default_copy()
        configuration.host = f"https://{host}:{port}"
        configuration.ssl_ca_cert = ca_path
        configuration.api_key = {"authorization": token}
        configuration.api_key_prefix = {"authorization": "Bearer"}
        client.Configuration.set_default(configuration)

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

        self._ensure_kubernetes_bearer_token()
        self._api = client.CustomObjectsApi()
        return self._api

    def submit(
        self,
        *,
        config_path: str,
        output_path: str,
        split_by: str,
        backtest_id: str,
        config_yaml: str | None = None,
    ) -> tuple[str, str]:
        workflow_name = f"backtest-{backtest_id[:12]}-{uuid.uuid4().hex[:6]}"
        if self.config.uses_http:
            return self._submit_via_http(
                workflow_name=workflow_name,
                config_path=config_path,
                output_path=output_path,
                split_by=split_by,
                backtest_id=backtest_id,
                config_yaml=config_yaml,
            )
        return self._submit_via_kubernetes(
            workflow_name=workflow_name,
            config_path=config_path,
            output_path=output_path,
            split_by=split_by,
            backtest_id=backtest_id,
            config_yaml=config_yaml,
        )

    def _submit_via_http(
        self,
        *,
        workflow_name: str,
        config_path: str,
        output_path: str,
        split_by: str,
        backtest_id: str,
        config_yaml: str | None = None,
    ) -> tuple[str, str]:
        body = {
            "namespace": self.config.namespace,
            "serverDryRun": False,
            "workflow": self._build_workflow_resource(
                workflow_name=workflow_name,
                config_path=config_path,
                output_path=output_path,
                split_by=split_by,
                backtest_id=backtest_id,
                config_yaml=config_yaml,
            ),
        }
        response = self._http_request(
            "POST",
            f"/api/v1/workflows/{self.config.namespace}",
            json=body,
        )
        if response.status_code >= 400:
            raise RuntimeError(f"Failed to submit Argo workflow: {response.status_code} {response.text}")
        return workflow_name, self.config.namespace

    def _submit_via_kubernetes(
        self,
        *,
        workflow_name: str,
        config_path: str,
        output_path: str,
        split_by: str,
        backtest_id: str,
        config_yaml: str | None = None,
    ) -> tuple[str, str]:
        api = self._custom_objects_api()
        body = self._build_workflow_resource(
            workflow_name=workflow_name,
            config_path=config_path,
            output_path=output_path,
            split_by=split_by,
            backtest_id=backtest_id,
            config_yaml=config_yaml,
        )
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
        if self.config.uses_http:
            return self._get_workflow_phase_via_http(workflow_name)
        return self._get_workflow_phase_via_kubernetes(workflow_name)

    def _get_workflow_phase_via_http(self, workflow_name: str) -> str | None:
        response = self._http_request(
            "GET",
            f"/api/v1/workflows/{self.config.namespace}/{workflow_name}",
        )
        if response.status_code == 404:
            return None
        if response.status_code >= 400:
            return None
        payload = response.json()
        if not isinstance(payload, dict):
            return None
        return _phase_from_workflow_resource(payload)

    def _get_workflow_phase_via_kubernetes(self, workflow_name: str) -> str | None:
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
        if not isinstance(resource, dict):
            return None
        return _phase_from_workflow_resource(resource)

    def list_workflows_for_backtest(self, backtest_id: str) -> list[dict[str, Any]]:
        if self.config.uses_http:
            return self._list_workflows_for_backtest_via_http(backtest_id)
        return self._list_workflows_for_backtest_via_kubernetes(backtest_id)

    def _list_workflows_for_backtest_via_http(self, backtest_id: str) -> list[dict[str, Any]]:
        response = self._http_request(
            "GET",
            f"/api/v1/workflows/{self.config.namespace}",
            params={"listOptions.labelSelector": f"backtest-id={backtest_id}"},
        )
        if response.status_code >= 400:
            return []
        payload = response.json()
        if not isinstance(payload, dict):
            return []
        items = payload.get("items")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def _list_workflows_for_backtest_via_kubernetes(self, backtest_id: str) -> list[dict[str, Any]]:
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
