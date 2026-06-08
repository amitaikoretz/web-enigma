from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import httpx
import pytest

from app.market_overview.argo import MarketOverviewArgoConfig, MarketOverviewArgoSubmitter
from app.market_overview.argo_workflow import build_market_overview_workflow_spec


def _submission_payload_from_record(record: logging.LogRecord) -> dict[str, object]:
    message = record.getMessage()
    payload_text = message.split(" payload=", 1)[1]
    return json.loads(payload_text)


def test_build_market_overview_workflow_spec_uses_valid_container_resources() -> None:
    spec = build_market_overview_workflow_spec(
        snapshot_id="snap-123",
        output_path="/data/market-overview-results/snap-123/snap-123.json",
    )

    assert spec["volumes"] == [
        {
            "name": "market-overview-results",
            "persistentVolumeClaim": {"claimName": "backtest-results"},
        }
    ]

    workflow = next(item for item in spec["templates"] if item["name"] == "market-overview")
    step_names = [step["name"] for group in workflow["steps"] for step in group]
    assert step_names == ["print-payload", "generate-snapshot", "reconcile-snapshot"]

    print_payload = next(item for item in spec["templates"] if item["name"] == "print-payload")
    args = print_payload["container"]["args"]
    assert "__COMMAND_LINE__" not in args
    assert "--command-line" in args

    generate_snapshot = next(item for item in spec["templates"] if item["name"] == "generate-snapshot")
    reconcile_snapshot = next(item for item in spec["templates"] if item["name"] == "reconcile-snapshot")

    for template in (generate_snapshot, reconcile_snapshot):
        assert "podSpecPatch" not in template
        resources = template["container"]["resources"]
        assert resources == {
            "requests": {"memory": "1Gi"},
            "limits": {"memory": "1Gi"},
        }


def test_build_market_overview_workflow_spec_falls_back_from_bad_results_claim(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MARKET_OVERVIEW_RESULTS_CLAIM", "market-overview-results")

    spec = build_market_overview_workflow_spec(
        snapshot_id="snap-123",
        output_path="/data/market-overview-results/snap-123/snap-123.json",
    )

    assert spec["volumes"] == [
        {
            "name": "market-overview-results",
            "persistentVolumeClaim": {"claimName": "backtest-results"},
        }
    ]


def test_submit_via_http_posts_workflow_to_argo_server(caplog: pytest.LogCaptureFixture) -> None:
    config = MarketOverviewArgoConfig(
        namespace="backtest-workflows",
        enabled=True,
        server_url="https://argo.example:2746",
        token="secret-token",
    )
    submitter = MarketOverviewArgoSubmitter(config)
    mock_client = MagicMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = ""
    mock_client.request.return_value = mock_response
    submitter._http_client = mock_client
    caplog.set_level(logging.INFO)

    workflow_name, namespace = submitter.submit(
        snapshot_id="snap-1234567890",
        output_path="/data/market-overview-results/snap-1234567890/snap-1234567890.json",
    )

    assert namespace == "backtest-workflows"
    assert workflow_name.startswith("market-overview-snap-123456")
    mock_client.request.assert_called_once()
    method, url = mock_client.request.call_args.args[:2]
    assert method == "POST"
    assert url == "https://argo.example:2746/api/v1/workflows/backtest-workflows"
    headers = mock_client.request.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret-token"
    body = mock_client.request.call_args.kwargs["json"]
    assert body["namespace"] == "backtest-workflows"
    workflow = body["workflow"]
    assert workflow["metadata"]["name"] == workflow_name
    assert workflow["metadata"]["labels"]["market-overview-id"] == "snap-1234567890"
    assert workflow["spec"]["entrypoint"] == "market-overview"
    assert "workflowTemplateRef" not in workflow["spec"]
    template = next(item for item in workflow["spec"]["templates"] if item["name"] == "generate-snapshot")
    assert template["container"]["resources"] == {
        "requests": {"memory": "1Gi"},
        "limits": {"memory": "1Gi"},
    }

    submission_records = [record for record in caplog.records if "argo workflow submission" in record.getMessage()]
    assert len(submission_records) == 1
    submission_record = submission_records[0]
    assert "endpoint=market_overview.argo.submit" in submission_record.getMessage()
    assert "route=POST /api/v1/workflows/backtest-workflows" in submission_record.getMessage()
    assert _submission_payload_from_record(submission_record) == body


def test_submit_via_http_raises_on_error_response() -> None:
    submitter = MarketOverviewArgoSubmitter(
        MarketOverviewArgoConfig(
            namespace="backtest-workflows",
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
            snapshot_id="snap-1234567890",
            output_path="/data/market-overview-results/snap-1234567890/snap-1234567890.json",
        )
