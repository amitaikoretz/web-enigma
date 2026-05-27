from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.backtests.argo import ArgoWorkflowConfig, ArgoWorkflowSubmitter, load_argo_workflow_config
from app.backtests.argo_workflow import WORKFLOW_TTL_SECONDS, build_backtest_workflow_spec, workflow_results_mount


def test_build_backtest_workflow_spec_inlines_batch_definition() -> None:
    spec = build_backtest_workflow_spec(
        config_path="/data/config.yaml",
        output_path="/data/output.json",
        split_by="symbol",
        backtest_id="abc123",
    )

    assert spec["entrypoint"] == "backtest-batch"
    assert spec["serviceAccountName"] == "backtest-workflow"
    assert spec["ttlStrategy"] == {"secondsAfterCompletion": WORKFLOW_TTL_SECONDS}
    assert "workflowTemplateRef" not in spec
    template_names = {template["name"] for template in spec["templates"]}
    assert template_names == {
        "backtest-batch",
        "print-payload",
        "plan-shards",
        "run-shard",
        "merge-reports",
    }
    parameters = {item["name"]: item["value"] for item in spec["arguments"]["parameters"]}
    assert parameters == {
        "api-base-url": "http://api.backtest.svc.cluster.local:8000",
        "config-path": "/data/config.yaml",
        "output-path": "/data/output.json",
        "split-by": "symbol",
        "backtest-id": "abc123",
        "config-b64": "",
    }

    batch_template = next(item for item in spec["templates"] if item["name"] == "backtest-batch")
    step_names = [step["name"] for group in batch_template["steps"] for step in group]
    assert step_names == ["print-payload", "plan", "run-shards", "merge"]

    merge_step = batch_template["steps"][3][0]
    merge_params = {item["name"]: item["value"] for item in merge_step["arguments"]["parameters"]}
    assert merge_params["manifest-path"] == "{{steps.plan.outputs.parameters.manifest-path}}"

    plan_step = batch_template["steps"][1][0]
    plan_params = {item["name"]: item["value"] for item in plan_step["arguments"]["parameters"]}
    assert plan_params["config-path"] == "{{workflow.parameters.config-path}}"

    print_payload_template = next(
        item for item in spec["templates"] if item["name"] == "print-payload"
    )
    launch_curl_output = print_payload_template["outputs"]["parameters"][0]
    assert launch_curl_output == {
        "name": "launch-curl",
        "valueFrom": {"path": "/tmp/launch-curl.txt"},
    }
    assert "/tmp/launch-curl.txt" in print_payload_template["container"]["args"]


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
    output_paths = {
        item["name"]: item["valueFrom"]["path"] for item in plan_template["outputs"]["parameters"]
    }
    assert output_paths == {
        "shards": "/tmp/shards-param.json",
        "manifest-path": "/tmp/manifest-path.txt",
        "work-dir": "/tmp/work-dir.txt",
    }
    plan_script = plan_template["container"]["args"][0]
    assert f'{workflow_results_mount()}/{{{{inputs.parameters.backtest-id}}}}' in plan_script
    assert "/tmp/manifest-path.txt" in plan_script
    run_shard = next(item for item in spec["templates"] if item["name"] == "run-shard")
    run_inputs = {item["name"] for item in run_shard["inputs"]["parameters"]}
    assert run_inputs == {"shard-id", "shard-config-path", "shard-output-path"}
    mount_names = {mount["name"] for mount in run_shard["container"]["volumeMounts"]}
    assert "backtest-results" in mount_names
    merge_template = next(item for item in spec["templates"] if item["name"] == "merge-reports")
    merge_script = merge_template["container"]["args"][0]
    assert '{{inputs.parameters.manifest-path}}' in merge_script
    assert "/tmp/merged-output-path.txt" in merge_script


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


def test_build_backtest_workflow_spec_uses_configured_api_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKTEST_API_BASE_URL", "http://localhost:8000")

    spec = build_backtest_workflow_spec(
        config_path="/data/config.yaml",
        output_path="/data/output.json",
        split_by="symbol",
        backtest_id="abc123",
    )

    parameters = {item["name"]: item["value"] for item in spec["arguments"]["parameters"]}
    assert parameters["api-base-url"] == "http://localhost:8000"


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


def test_ensure_kubernetes_bearer_token_uses_bearer_token_key(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_dir = tmp_path / "token"
    token_dir.mkdir()
    token_file = token_dir / "token"
    token_file.write_text("test-sa-token", encoding="utf-8")
    ca_file = token_dir / "ca.crt"
    ca_file.write_text("fake-ca", encoding="utf-8")

    monkeypatch.setenv("KUBERNETES_SERVICE_HOST", "10.43.0.1")
    monkeypatch.setenv("KUBERNETES_SERVICE_PORT_HTTPS", "443")
    monkeypatch.setattr(
        "app.backtests.argo.os.path.exists",
        lambda path: str(path).endswith("token") or str(path).endswith("ca.crt"),
    )

    submitter = ArgoWorkflowSubmitter(ArgoWorkflowConfig(namespace="backtest-workflows", enabled=True))
    with patch("builtins.open", side_effect=[token_file.open(), ca_file.open()]):
        submitter._ensure_kubernetes_bearer_token()

    from kubernetes import client

    configuration = client.Configuration.get_default_copy()
    assert configuration.api_key == {"BearerToken": "test-sa-token", "authorization": "test-sa-token"}
    assert configuration.api_key_prefix == {"BearerToken": "Bearer", "authorization": "Bearer"}
    assert configuration.get_api_key_with_prefix("BearerToken") == "Bearer test-sa-token"
