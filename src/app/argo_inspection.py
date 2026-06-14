from __future__ import annotations

import json
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kubernetes import client as k8s_client
from kubernetes import config as k8s_config
from kubernetes.client import ApiException

from app.backtests.argo import ArgoWorkflowSubmitter

_DEFAULT_SECRET_ENV_VARS = ("DATABASE_URL", "ALPACA_API_KEY", "ALPACA_SECRET_KEY")
logger = logging.getLogger(__name__)


class ArgoWorkflowInspectionError(RuntimeError):
    pass


class ArgoWorkflowNotFoundError(ArgoWorkflowInspectionError):
    pass


class ArgoWorkflowPodNotFoundError(ArgoWorkflowInspectionError):
    pass


@dataclass(frozen=True)
class DebugConfigurationResult:
    workflow_name: str
    namespace: str
    pod_name: str
    terminal_command: str
    launch_configuration: dict[str, Any]
    snippet: str


@dataclass(frozen=True)
class PodLogsResult:
    workflow_name: str
    namespace: str
    pod_name: str
    container_name: str | None
    logs: str


def _workflow_status(workflow: dict[str, Any]) -> dict[str, Any]:
    status = workflow.get("status")
    return status if isinstance(status, dict) else {}


def _workflow_nodes(workflow: dict[str, Any]) -> dict[str, Any]:
    nodes = _workflow_status(workflow).get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _workflow_spec(workflow: dict[str, Any]) -> dict[str, Any]:
    spec = workflow.get("spec")
    return spec if isinstance(spec, dict) else {}


def _workflow_templates(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    templates = _workflow_spec(workflow).get("templates")
    if not isinstance(templates, list):
        return []
    return [item for item in templates if isinstance(item, dict)]


def _template_by_name(workflow: dict[str, Any], name: str | None) -> dict[str, Any] | None:
    if not name:
        return None
    for template in _workflow_templates(workflow):
        if template.get("name") == name:
            return template
    return None


def _node_pod_name(node: dict[str, Any]) -> str | None:
    pod_name = node.get("podName")
    if isinstance(pod_name, str) and pod_name.strip():
        return pod_name.strip()
    return None


def _node_by_pod_name(workflow: dict[str, Any], pod_name: str) -> dict[str, Any] | None:
    nodes = _workflow_nodes(workflow)
    for node in nodes.values():
        if not isinstance(node, dict):
            continue
        if _node_pod_name(node) == pod_name:
            return node
    return None


def _node_output_parameters(node: dict[str, Any]) -> list[dict[str, Any]]:
    outputs = node.get("outputs")
    if not isinstance(outputs, dict):
        return []
    parameters = outputs.get("parameters")
    if not isinstance(parameters, list):
        return []
    return [item for item in parameters if isinstance(item, dict)]


def _node_output_value(node: dict[str, Any], *names: str) -> str | None:
    for item in _node_output_parameters(node):
        if item.get("name") not in names:
            continue
        value = item.get("value")
        if isinstance(value, str):
            text = value.strip()
            return text or None
        if value is not None:
            text = str(value).strip()
            return text or None
    return None


def _normalize_path_for_workspace(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("/workspace/"):
        return "${workspaceFolder}/" + normalized.removeprefix("/workspace/")
    if normalized == "/workspace":
        return "${workspaceFolder}"
    return path


def _parse_terminal_command(terminal_command: str) -> list[str]:
    return shlex.split(terminal_command)


def _is_python_executable(token: str) -> bool:
    base = Path(token).name
    return base in {"python", "python3", "python.exe", "python3.exe"}


def _looks_like_kalyxctl(token: str) -> bool:
    return Path(token).name == "kalyxctl"


def _build_launch_configuration(command_parts: list[str], *, pod_name: str, workflow_name: str) -> dict[str, Any]:
    if not command_parts:
        raise ValueError("Terminal command is empty")

    env: dict[str, str] = {
        "PYTHONPATH": "${workspaceFolder}/src",
    }
    env.update({name: f"${{env:{name}}}" for name in _DEFAULT_SECRET_ENV_VARS})

    launch_config: dict[str, Any] = {
        "name": f"Debug {pod_name} ({workflow_name})",
        "type": "debugpy",
        "request": "launch",
        "python": "${command:python.interpreterPath}",
        "cwd": "${workspaceFolder}",
        "console": "integratedTerminal",
        "env": env,
        "justMyCode": True,
    }

    if _is_python_executable(command_parts[0]):
        if len(command_parts) >= 3 and command_parts[1] == "-m":
            launch_config["module"] = command_parts[2]
            launch_config["args"] = command_parts[3:]
            return launch_config

        if len(command_parts) >= 2:
            launch_config["program"] = _normalize_path_for_workspace(command_parts[1])
            launch_config["args"] = command_parts[2:]
            return launch_config

    if _looks_like_kalyxctl(command_parts[0]):
        launch_config["module"] = "app.cli"
        launch_config["args"] = command_parts[1:]
        return launch_config

    launch_config["program"] = _normalize_path_for_workspace(command_parts[0])
    launch_config["args"] = command_parts[1:]
    return launch_config


def _format_launch_snippet(launch_configuration: dict[str, Any]) -> str:
    return json.dumps(launch_configuration, indent=2, sort_keys=False)


def _build_core_v1_api() -> k8s_client.CoreV1Api:
    try:
        k8s_config.load_incluster_config()
    except Exception:
        k8s_config.load_kube_config()
    return k8s_client.CoreV1Api()


def _pod_container_name(pod: Any) -> str | None:
    spec = getattr(pod, "spec", None)
    containers = getattr(spec, "containers", None)
    if not containers:
        return None
    preferred: list[str] = []
    for container in containers:
        name = getattr(container, "name", None)
        if isinstance(name, str) and name.strip():
            preferred.append(name.strip())
    if not preferred:
        return None
    for candidate in preferred:
        if candidate not in {"wait", "argoexec"} and not candidate.startswith("argo"):
            return candidate
    return preferred[0]


def _api_exception_text(exc: ApiException) -> str:
    parts = [getattr(exc, "reason", None), getattr(exc, "body", None), str(exc)]
    return "\n".join(
        part.strip() for part in parts if isinstance(part, str) and part.strip()
    )


def _is_missing_pod_log_path(exc: ApiException) -> bool:
    text = _api_exception_text(exc).lower()
    return (
        "failed to try resolving symlinks in path" in text
        or "no such file or directory" in text
        or "file does not exist" in text
        or ("not found" in text and "/var/log/pods" in text)
    )


@dataclass
class ArgoWorkflowInspectionService:
    submitter: ArgoWorkflowSubmitter

    def get_workflow(self, workflow_name: str, *, namespace: str | None = None) -> dict[str, Any]:
        response = self.submitter.get_workflow_response(workflow_name, namespace=namespace)
        if response.status_code == 404:
            raise ArgoWorkflowNotFoundError(f"Workflow '{workflow_name}' not found")
        if response.status_code >= 400:
            raise ArgoWorkflowInspectionError(
                f"Failed to load Argo workflow '{workflow_name}': {response.status_code} {response.text}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ArgoWorkflowInspectionError(
                f"Workflow '{workflow_name}' did not return a JSON object"
            )
        return payload

    def build_debug_configuration(
        self,
        workflow_name: str,
        pod_name: str,
        *,
        namespace: str | None = None,
    ) -> DebugConfigurationResult:
        workflow = self.get_workflow(workflow_name, namespace=namespace)
        node = _node_by_pod_name(workflow, pod_name)
        if node is None:
            raise ArgoWorkflowPodNotFoundError(
                f"Pod '{pod_name}' was not found in workflow '{workflow_name}'"
            )

        terminal_command = _node_output_value(node, "terminal-command", "commandLine")
        if terminal_command is None:
            raise ArgoWorkflowInspectionError(
                f"Pod '{pod_name}' in workflow '{workflow_name}' did not expose a terminal command output"
            )

        command_parts = _parse_terminal_command(terminal_command)
        template = _template_by_name(workflow, str(node.get("templateName") or "")) or {}
        launch_configuration = _build_launch_configuration(
            command_parts,
            pod_name=pod_name,
            workflow_name=workflow_name,
        )

        container = template.get("container")
        if isinstance(container, dict):
            # Preserve any non-secret literal environment values declared by the pod template.
            env = launch_configuration.setdefault("env", {})
            if isinstance(env, dict):
                container_env = container.get("env")
                for item in container_env if isinstance(container_env, list) else []:
                    if not isinstance(item, dict):
                        continue
                    name = item.get("name")
                    if not isinstance(name, str) or not name.strip():
                        continue
                    if name in env:
                        continue
                    value = item.get("value")
                    if isinstance(value, str):
                        env[name] = value
                        continue
                    value_from = item.get("valueFrom")
                    if isinstance(value_from, dict):
                        secret_key_ref = value_from.get("secretKeyRef")
                        if isinstance(secret_key_ref, dict):
                            key = secret_key_ref.get("key")
                            if isinstance(key, str) and key.strip():
                                env[name] = f"${{env:{key.strip()}}}"

                env_from = container.get("envFrom")
                if isinstance(env_from, list):
                    has_secret_ref = any(
                        isinstance(entry, dict) and isinstance(entry.get("secretRef"), dict)
                        for entry in env_from
                    )
                    if has_secret_ref:
                        for secret_env_name in _DEFAULT_SECRET_ENV_VARS:
                            env.setdefault(secret_env_name, f"${{env:{secret_env_name}}}")

        snippet = _format_launch_snippet(launch_configuration)
        return DebugConfigurationResult(
            workflow_name=workflow_name,
            namespace=namespace or self.submitter.config.namespace,
            pod_name=pod_name,
            terminal_command=terminal_command,
            launch_configuration=launch_configuration,
            snippet=snippet,
        )

    def get_pod_logs(
        self,
        workflow_name: str,
        pod_name: str,
        *,
        namespace: str | None = None,
    ) -> PodLogsResult:
        workflow = self.get_workflow(workflow_name, namespace=namespace)
        node = _node_by_pod_name(workflow, pod_name)
        if node is None:
            raise ArgoWorkflowPodNotFoundError(
                f"Pod '{pod_name}' was not found in workflow '{workflow_name}'"
            )

        target_namespace = namespace or self.submitter.config.namespace
        try:
            api = _build_core_v1_api()
        except Exception as exc:  # pragma: no cover - config errors are environment-specific
            raise ArgoWorkflowInspectionError(f"Failed to initialize Kubernetes client: {exc}") from exc

        try:
            pod = api.read_namespaced_pod(name=pod_name, namespace=target_namespace)
        except ApiException as exc:
            if exc.status == 404:
                raise ArgoWorkflowPodNotFoundError(
                    f"Pod '{pod_name}' was not found in namespace '{target_namespace}'"
                ) from exc
            raise ArgoWorkflowInspectionError(
                f"Failed to read pod '{pod_name}' from namespace '{target_namespace}': {exc}"
            ) from exc

        container_name = _pod_container_name(pod)
        try:
            logs = api.read_namespaced_pod_log(
                name=pod_name,
                namespace=target_namespace,
                container=container_name,
                timestamps=True,
                tail_lines=2000,
            )
        except ApiException as exc:
            if exc.status == 404 or _is_missing_pod_log_path(exc):
                logger.warning(
                    "Pod logs unavailable for workflow '%s' pod '%s' in namespace '%s': %s",
                    workflow_name,
                    pod_name,
                    target_namespace,
                    _api_exception_text(exc),
                )
                return PodLogsResult(
                    workflow_name=workflow_name,
                    namespace=target_namespace,
                    pod_name=pod_name,
                    container_name=container_name,
                    logs="",
                )
            raise ArgoWorkflowInspectionError(
                f"Failed to read logs for pod '{pod_name}' in namespace '{target_namespace}': {exc}"
            ) from exc

        return PodLogsResult(
            workflow_name=workflow_name,
            namespace=target_namespace,
            pod_name=pod_name,
            container_name=container_name,
            logs=logs if isinstance(logs, str) else str(logs),
        )
