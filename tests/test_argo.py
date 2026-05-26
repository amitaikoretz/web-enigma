from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.backtests.argo import ArgoWorkflowConfig, ArgoWorkflowSubmitter, load_argo_workflow_config
from app.backtests.argo_workflow import build_backtest_workflow_spec


def test_build_backtest_workflow_spec_inlines_batch_definition() -> None:
    spec = build_backtest_workflow_spec(
        config_path="/data/config.yaml",
        output_path="/data/output.json",
        split_by="symbol",
        backtest_id="abc123",
    )

    assert spec["entrypoint"] == "backtest-batch"
    assert spec["serviceAccountName"] == "backtest-workflow"
    assert "workflowTemplateRef" not in spec
    template_names = {template["name"] for template in spec["templates"]}
    assert template_names == {"backtest-batch", "plan-shards", "run-shard", "merge-reports"}
    parameters = {item["name"]: item["value"] for item in spec["arguments"]["parameters"]}
    assert parameters == {
        "config-path": "/data/config.yaml",
        "output-path": "/data/output.json",
        "split-by": "symbol",
        "backtest-id": "abc123",
        "config-b64": "",
    }


def test_build_backtest_workflow_spec_embeds_config_yaml() -> None:
    spec = build_backtest_workflow_spec(
        config_path="/data/backtest-results/job.yaml",
        output_path="/data/backtest-results/job.json",
        split_by="symbol",
        backtest_id="abc123",
        config_yaml="runs: []\n",
    )

    parameters = {item["name"]: item["value"] for item in spec["arguments"]["parameters"]}
    assert parameters["config-b64"] == "cnVuczogW10K"
    plan_template = next(item for item in spec["templates"] if item["name"] == "plan-shards")
    assert plan_template["outputs"]["parameters"][0]["valueFrom"]["path"] == "/tmp/shards-param.json"


def test_build_backtest_workflow_spec_uses_configured_service_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ARGO_WORKFLOW_SERVICE_ACCOUNT", "workflow-runner")

    spec = build_backtest_workflow_spec(
        config_path="/data/config.yaml",
        output_path="/data/output.json",
        split_by="symbol",
        backtest_id="abc123",
    )

    assert spec["serviceAccountName"] == "workflow-runner"


def test_load_config_enables_when_argo_server_url_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BACKTEST_ARGO_ENABLED", raising=False)
    monkeypatch.delenv("KUBERNETES_SERVICE_HOST", raising=False)
    monkeypatch.setenv("ARGO_SERVER_URL", "https://argo.example:2746/")

    config = load_argo_workflow_config()

    assert config.enabled is True
    assert config.server_url == "https://argo.example:2746"
    assert config.uses_http is True


def test_is_configured_true_for_http_mode_without_kubernetes() -> None:
    submitter = ArgoWorkflowSubmitter(
        ArgoWorkflowConfig(
            namespace="backtest",
            enabled=True,
            server_url="https://argo.example:2746",
        )
    )

    assert submitter.is_configured is True


def test_submit_via_http_posts_workflow_to_argo_server() -> None:
    config = ArgoWorkflowConfig(
        namespace="backtest",
        enabled=True,
        server_url="https://argo.example:2746",
        token="secret-token",
    )
    submitter = ArgoWorkflowSubmitter(config)
    mock_client = MagicMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = ""
    mock_client.request.return_value = mock_response
    submitter._http_client = mock_client

    workflow_name, namespace = submitter.submit(
        config_path="/data/config.yaml",
        output_path="/data/output.json",
        split_by="symbol",
        backtest_id="abc123def456",
    )

    assert namespace == "backtest"
    assert workflow_name.startswith("backtest-abc123def456-")
    mock_client.request.assert_called_once()
    method, url = mock_client.request.call_args.args[:2]
    assert method == "POST"
    assert url == "https://argo.example:2746/api/v1/workflows/backtest"
    headers = mock_client.request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-token"
    body = mock_client.request.call_args.kwargs["json"]
    assert body["namespace"] == "backtest"
    workflow = body["workflow"]
    assert workflow["metadata"]["name"] == workflow_name
    assert workflow["metadata"]["labels"]["backtest-id"] == "abc123def456"
    assert workflow["spec"]["entrypoint"] == "backtest-batch"
    assert "workflowTemplateRef" not in workflow["spec"]


def test_submit_via_http_raises_on_error_response() -> None:
    submitter = ArgoWorkflowSubmitter(
        ArgoWorkflowConfig(
            namespace="backtest",
            enabled=True,
            server_url="https://argo.example:2746",
        )
    )
    mock_client = MagicMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 403
    mock_response.text = "forbidden"
    mock_client.request.return_value = mock_response
    submitter._http_client = mock_client

    with pytest.raises(RuntimeError, match="Failed to submit Argo workflow: 403 forbidden"):
        submitter.submit(
            config_path="/data/config.yaml",
            output_path="/data/output.json",
            split_by="symbol",
            backtest_id="abc123",
        )


def test_get_workflow_phase_via_http() -> None:
    submitter = ArgoWorkflowSubmitter(
        ArgoWorkflowConfig(
            namespace="backtest",
            enabled=True,
            server_url="https://argo.example:2746",
        )
    )
    mock_client = MagicMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": {"phase": "Succeeded"}}
    mock_client.request.return_value = mock_response
    submitter._http_client = mock_client

    assert submitter.get_workflow_phase("backtest-abc") == "Succeeded"


def test_list_workflows_for_backtest_via_http() -> None:
    submitter = ArgoWorkflowSubmitter(
        ArgoWorkflowConfig(
            namespace="backtest",
            enabled=True,
            server_url="https://argo.example:2746",
        )
    )
    mock_client = MagicMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {"items": [{"metadata": {"name": "backtest-abc"}}]}
    mock_client.request.return_value = mock_response
    submitter._http_client = mock_client

    workflows = submitter.list_workflows_for_backtest("abc123")

    assert workflows == [{"metadata": {"name": "backtest-abc"}}]
    _, url = mock_client.request.call_args.args[:2]
    params = mock_client.request.call_args.kwargs["params"]
    assert params == {"listOptions.labelSelector": "backtest-id=abc123"}
    assert url == "https://argo.example:2746/api/v1/workflows/backtest"


def test_submit_via_http_raises_helpful_message_for_tls_scheme_mismatch() -> None:
    submitter = ArgoWorkflowSubmitter(
        ArgoWorkflowConfig(
            namespace="backtest",
            enabled=True,
            server_url="https://argo.example:2746",
        )
    )
    mock_client = MagicMock()
    mock_client.request.side_effect = httpx.ConnectError(
        "[SSL: WRONG_VERSION_NUMBER] wrong version number",
        request=httpx.Request("POST", "https://argo.example:2746/api/v1/workflows/backtest"),
    )
    submitter._http_client = mock_client

    with pytest.raises(RuntimeError, match="speaking plain HTTP.*http://argo.example:2746"):
        submitter.submit(
            config_path="/data/config.yaml",
            output_path="/data/output.json",
            split_by="symbol",
            backtest_id="abc123",
        )


@patch("app.backtests.argo.ArgoWorkflowSubmitter._custom_objects_api")
def test_submit_via_kubernetes_when_server_url_not_set(mock_custom_objects_api: MagicMock) -> None:
    api = MagicMock()
    mock_custom_objects_api.return_value = api
    submitter = ArgoWorkflowSubmitter(
        ArgoWorkflowConfig(
            namespace="backtest",
            enabled=True,
        )
    )

    workflow_name, namespace = submitter.submit(
        config_path="/data/config.yaml",
        output_path="/data/output.json",
        split_by="symbol",
        backtest_id="abc123def456",
    )

    assert namespace == "backtest"
    assert workflow_name.startswith("backtest-abc123def456-")
    api.create_namespaced_custom_object.assert_called_once()
    body = api.create_namespaced_custom_object.call_args.kwargs["body"]
    assert body["metadata"]["name"] == workflow_name
    assert body["spec"]["entrypoint"] == "backtest-batch"
    assert "workflowTemplateRef" not in body["spec"]
