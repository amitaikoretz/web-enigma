from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.conftest import build_backtest_client


class _FakeResponse:
    def __init__(self, status_code: int, payload: object, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self) -> object:
        return self._payload


def _workflow_payload(*, terminal_command_key: str = "terminal-command") -> dict[str, object]:
    return {
        "metadata": {"name": "wf-1", "namespace": "backtest-workflows"},
        "spec": {
            "templates": [
                {
                    "name": "main",
                    "container": {
                        "image": "backtest-app:latest",
                        "command": ["python", "-m", "app.standalone.run_scan_trend_argo"],
                        "args": [
                            "--scan-id",
                            "scan-123",
                        ],
                        "env": [
                            {"name": "LOG_LEVEL", "value": "debug"},
                        ],
                        "envFrom": [
                            {"secretRef": {"name": "app-secrets"}},
                        ],
                    },
                }
            ]
        },
        "status": {
            "phase": "Running",
            "nodes": {
                "node-1": {
                    "podName": "pod-1",
                    "templateName": "main",
                    "outputs": {
                        "parameters": [
                            {"name": terminal_command_key, "value": "python -m app.standalone.run_scan_trend_argo --scan-id scan-123"},
                        ]
                    },
                }
            },
        },
    }


def test_get_argo_workflow_json_returns_workflow_payload(tmp_path) -> None:
    client = build_backtest_client(tmp_path)
    submitter = client.app.state.deps.backtest_jobs.argo_submitter
    submitter.get_workflow_response = lambda workflow_name, *, namespace=None: _FakeResponse(  # type: ignore[method-assign]
        200,
        _workflow_payload(),
    )

    response = client.get("/argo/workflows/wf-1")

    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["name"] == "wf-1"
    assert body["spec"]["templates"][0]["name"] == "main"


def test_get_argo_workflow_json_returns_404_for_missing_workflow(tmp_path) -> None:
    client = build_backtest_client(tmp_path)
    submitter = client.app.state.deps.backtest_jobs.argo_submitter
    submitter.get_workflow_response = lambda workflow_name, *, namespace=None: _FakeResponse(  # type: ignore[method-assign]
        404,
        {"message": "not found"},
        text="not found",
    )

    response = client.get("/argo/workflows/missing")

    assert response.status_code == 404


def test_get_argo_workflow_debug_config_builds_launch_snippet_without_secrets(tmp_path) -> None:
    client = build_backtest_client(tmp_path)
    submitter = client.app.state.deps.backtest_jobs.argo_submitter
    submitter.get_workflow_response = lambda workflow_name, *, namespace=None: _FakeResponse(  # type: ignore[method-assign]
        200,
        _workflow_payload(),
    )

    response = client.get("/argo/workflows/wf-1/pods/pod-1/debug-config")

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_name"] == "wf-1"
    assert body["pod_name"] == "pod-1"
    assert body["terminal_command"] == "python -m app.standalone.run_scan_trend_argo --scan-id scan-123"
    launch = body["launch_configuration"]
    assert launch["type"] == "debugpy"
    assert launch["module"] == "app.standalone.run_scan_trend_argo"
    assert launch["args"] == ["--scan-id", "scan-123"]
    assert launch["env"]["PYTHONPATH"] == "${workspaceFolder}/src"
    assert launch["env"]["LOG_LEVEL"] == "debug"
    assert launch["env"]["DATABASE_URL"] == "${env:DATABASE_URL}"
    assert launch["env"]["ALPACA_API_KEY"] == "${env:ALPACA_API_KEY}"
    assert launch["env"]["ALPACA_SECRET_KEY"] == "${env:ALPACA_SECRET_KEY}"
    assert "${env:" in body["snippet"]
    assert "secret-value" not in body["snippet"]


def test_get_argo_workflow_debug_config_accepts_legacy_command_line_output(tmp_path) -> None:
    client = build_backtest_client(tmp_path)
    submitter = client.app.state.deps.backtest_jobs.argo_submitter
    payload = _workflow_payload(terminal_command_key="commandLine")
    payload["status"]["nodes"]["node-1"]["outputs"]["parameters"][0]["value"] = "kalyxctl universes sync-registry"  # type: ignore[index]
    submitter.get_workflow_response = lambda workflow_name, *, namespace=None: _FakeResponse(  # type: ignore[method-assign]
        200,
        payload,
    )

    response = client.get("/argo/workflows/wf-1/pods/pod-1/debug-config")

    assert response.status_code == 200
    body = response.json()
    assert body["terminal_command"] == "kalyxctl universes sync-registry"
    assert body["launch_configuration"]["module"] == "app.cli"
    assert body["launch_configuration"]["args"] == ["universes", "sync-registry"]


def test_get_argo_workflow_pod_logs_returns_pod_logs(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = build_backtest_client(tmp_path)
    submitter = client.app.state.deps.backtest_jobs.argo_submitter
    submitter.get_workflow_response = lambda workflow_name, *, namespace=None: _FakeResponse(  # type: ignore[method-assign]
        200,
        _workflow_payload(),
    )

    class _FakeCoreV1Api:
        def read_namespaced_pod(self, name: str, namespace: str) -> object:
            assert name == "pod-1"
            assert namespace == "backtest-workflows"
            return SimpleNamespace(
                spec=SimpleNamespace(
                    containers=[
                        SimpleNamespace(name="main"),
                        SimpleNamespace(name="wait"),
                    ]
                )
            )

        def read_namespaced_pod_log(
            self,
            name: str,
            namespace: str,
            container: str | None = None,
            timestamps: bool = True,
            tail_lines: int = 2000,
        ) -> str:
            assert name == "pod-1"
            assert namespace == "backtest-workflows"
            assert container == "main"
            assert timestamps is True
            assert tail_lines == 2000
            return "2026-06-04T12:00:00Z step started\n2026-06-04T12:00:03Z step finished"

    monkeypatch.setattr("app.argo_inspection._build_core_v1_api", lambda: _FakeCoreV1Api())
    response = client.get("/argo/workflows/wf-1/pods/pod-1/logs")

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_name"] == "wf-1"
    assert body["pod_name"] == "pod-1"
    assert body["container_name"] == "main"
    assert "step started" in body["logs"]
