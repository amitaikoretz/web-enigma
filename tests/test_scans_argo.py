from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import httpx
import pytest

from app.backtests.argo import ArgoWorkflowConfig, ArgoWorkflowSubmitter
from app.scans.argo import ScanArgoSubmitter


def _submission_payload_from_record(record: logging.LogRecord) -> dict[str, object]:
    message = record.getMessage()
    payload_text = message.split(" payload=", 1)[1]
    return json.loads(payload_text)


def test_scan_submitter_logs_submission_payload_and_endpoint(caplog: pytest.LogCaptureFixture) -> None:
    config = ArgoWorkflowConfig(
        namespace="backtest",
        enabled=True,
        server_url="https://argo.example:2746",
        token="secret-token",
    )
    http_submitter = ArgoWorkflowSubmitter(config)
    mock_client = MagicMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = ""
    mock_client.request.return_value = mock_response
    http_submitter._http_client = mock_client
    submitter = ScanArgoSubmitter(config=config, http_submitter=http_submitter)
    caplog.set_level(logging.INFO)

    workflow_name, namespace = submitter.submit(
        scan_type="momentum",
        scan_id="scan-1234567890",
        results_path="/tmp/scans/momentum/scan-1234567890/results.json",
        params_json='{"symbol":"AAPL"}',
    )

    assert namespace == "backtest"
    assert workflow_name.startswith("scan-momentum-scan-123456")
    mock_client.request.assert_called_once()
    method, url = mock_client.request.call_args.args[:2]
    assert method == "POST"
    assert url == "https://argo.example:2746/api/v1/workflows/backtest"
    body = mock_client.request.call_args.kwargs["json"]
    assert body["namespace"] == "backtest"
    assert body["workflow"]["metadata"]["labels"]["scan-id"] == "scan-1234567890"

    submission_records = [record for record in caplog.records if "argo workflow submission" in record.getMessage()]
    assert len(submission_records) == 1
    submission_record = submission_records[0]
    assert "endpoint=scans.argo.submit" in submission_record.getMessage()
    assert "route=POST /api/v1/workflows/backtest" in submission_record.getMessage()
    assert _submission_payload_from_record(submission_record) == body
