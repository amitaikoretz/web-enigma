from __future__ import annotations

import json
import logging
from unittest.mock import MagicMock

import httpx
import pytest

from app.backtests.argo import ArgoWorkflowConfig
from app.universes.argo import SymbolUniverseArgoConfig, SymbolUniverseWorkflowSubmitter


def _submission_payload_from_record(record: logging.LogRecord) -> dict[str, object]:
    message = record.getMessage()
    payload_text = message.split(" payload=", 1)[1]
    return json.loads(payload_text)


def test_submit_refresh_logs_submission_payload_and_endpoint(caplog: pytest.LogCaptureFixture) -> None:
    submitter = SymbolUniverseWorkflowSubmitter(
        config=SymbolUniverseArgoConfig(namespace="backtest-workflows", enabled=True),
        argo_config=ArgoWorkflowConfig(
            namespace="backtest-workflows",
            enabled=True,
            server_url="https://argo.example:2746",
            token="secret-token",
        ),
    )
    mock_client = MagicMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = ""
    mock_client.request.return_value = mock_response
    submitter._http_client = mock_client
    caplog.set_level(logging.INFO)

    workflow_name, namespace = submitter.submit_refresh(universe_key="abc", as_of="2026-06-07")

    assert namespace == "backtest-workflows"
    assert workflow_name.startswith("universe-refresh-")
    mock_client.request.assert_called_once()
    method, url = mock_client.request.call_args.args[:2]
    assert method == "POST"
    assert url == "https://argo.example:2746/api/v1/workflows/backtest-workflows"
    body = mock_client.request.call_args.kwargs["json"]
    assert body["namespace"] == "backtest-workflows"
    assert body["workflow"]["metadata"]["labels"]["app.kubernetes.io/component"] == "symbol-universe-refresh"

    submission_records = [record for record in caplog.records if "argo workflow submission" in record.getMessage()]
    assert len(submission_records) == 1
    submission_record = submission_records[0]
    assert "endpoint=universes.argo.submit_refresh" in submission_record.getMessage()
    assert "route=POST /api/v1/workflows/backtest-workflows" in submission_record.getMessage()
    assert _submission_payload_from_record(submission_record) == body


def test_submit_sync_registry_logs_submission_payload_and_endpoint(caplog: pytest.LogCaptureFixture) -> None:
    submitter = SymbolUniverseWorkflowSubmitter(
        config=SymbolUniverseArgoConfig(namespace="backtest-workflows", enabled=True),
        argo_config=ArgoWorkflowConfig(
            namespace="backtest-workflows",
            enabled=True,
            server_url="https://argo.example:2746",
        ),
    )
    mock_client = MagicMock()
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.text = ""
    mock_client.request.return_value = mock_response
    submitter._http_client = mock_client
    caplog.set_level(logging.INFO)

    workflow_name, namespace = submitter.submit_sync_registry()

    assert namespace == "backtest-workflows"
    assert workflow_name.startswith("universe-registry-sync-")
    mock_client.request.assert_called_once()
    method, url = mock_client.request.call_args.args[:2]
    assert method == "POST"
    assert url == "https://argo.example:2746/api/v1/workflows/backtest-workflows"
    body = mock_client.request.call_args.kwargs["json"]
    assert body["workflow"]["metadata"]["labels"]["app.kubernetes.io/component"] == "symbol-universe-registry-sync"

    submission_records = [record for record in caplog.records if "argo workflow submission" in record.getMessage()]
    assert len(submission_records) == 1
    submission_record = submission_records[0]
    assert "endpoint=universes.argo.submit_sync_registry" in submission_record.getMessage()
    assert "route=POST /api/v1/workflows/backtest-workflows" in submission_record.getMessage()
    assert _submission_payload_from_record(submission_record) == body
