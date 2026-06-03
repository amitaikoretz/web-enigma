from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import RiskModelGroup
from app.risk.workflow_errors import extract_workflow_error_details
from app.db.session import get_db_session

from tests.conftest import build_backtest_client


def test_extract_workflow_error_details_prefers_failed_leaf_outputs() -> None:
    workflow = {
        "status": {
            "phase": "Failed",
            "nodes": {
                "main": {
                    "phase": "Failed",
                    "displayName": "main",
                    "templateName": "main",
                    "children": ["train-stop"],
                },
                "train-stop": {
                    "phase": "Failed",
                    "displayName": "train-stop",
                    "templateName": "train-stop",
                    "finishedAt": "2026-06-01T12:01:00Z",
                    "outputs": {
                        "parameters": [
                            {"name": "error-exception", "value": "RuntimeError: boom"},
                            {"name": "error-code-location", "value": "/tmp/train.py:42"},
                            {"name": "error-call-stack", "value": "/tmp/train.py:42\n/tmp/train.py:13\n"},
                            {"name": "error-traceback", "value": "Traceback (most recent call last):\nboom"},
                        ]
                    },
                },
            }
        }
    }

    details = extract_workflow_error_details(workflow)

    assert details.available is True
    assert details.argo_phase == "Failed"
    assert details.failed_node_name == "train-stop"
    assert details.failed_template_name == "train-stop"
    assert details.error_exception == "RuntimeError: boom"
    assert details.error_code_location == "/tmp/train.py:42"
    assert details.error_call_stack == ["/tmp/train.py:42", "/tmp/train.py:13"]
    assert details.error_traceback == "Traceback (most recent call last):\nboom"


def test_extract_workflow_error_details_returns_unavailable_when_outputs_missing() -> None:
    workflow = {
        "status": {
            "phase": "Failed",
            "nodes": {
                "train-stop": {
                    "phase": "Failed",
                    "displayName": "train-stop",
                    "templateName": "train-stop",
                }
            },
        }
    }

    details = extract_workflow_error_details(workflow)

    assert details.available is False
    assert details.status_message == "The failed workflow step did not expose any error outputs."
    assert details.error_call_stack == []


def test_risk_model_workflow_errors_endpoint_returns_normalized_payload(tmp_path) -> None:
    client = build_backtest_client(tmp_path)
    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id="g1",
            status="failed",
            argo_namespace="ns",
            argo_workflow_name="wf",
            params_json={},
            artifact_dir=str(tmp_path / "risk-artifacts" / "g1"),
            summary_metrics_json=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    session.close()

    workflow = {
        "status": {
            "phase": "Failed",
            "nodes": {
                "main": {
                    "phase": "Failed",
                    "displayName": "main",
                    "templateName": "main",
                    "children": ["train-mae"],
                },
                "train-mae": {
                    "phase": "Failed",
                    "displayName": "train-mae",
                    "templateName": "train-mae",
                    "finishedAt": "2026-06-01T12:01:00Z",
                    "outputs": {
                        "parameters": [
                            {"name": "error-exception", "value": "ValueError: invalid feature"},
                            {"name": "error-code-location", "value": "/tmp/model.py:17"},
                            {"name": "error-call-stack", "value": "/tmp/model.py:17\n/tmp/train.py:61\n"},
                            {"name": "error-traceback", "value": "Traceback (most recent call last):\ninvalid feature"},
                        ]
                    },
                },
            }
        }
    }

    def fake_get_workflow(workflow_name: str, *, namespace: str | None = None):
        assert workflow_name == "wf"
        assert namespace == "ns"
        return workflow

    client.app.state.deps.risk_models._argo_submitter.get_workflow = fake_get_workflow  # type: ignore[method-assign]

    response = client.get("/risk-models/g1/workflow-errors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["group_id"] == "g1"
    assert payload["available"] is True
    assert payload["argo_namespace"] == "ns"
    assert payload["argo_workflow_name"] == "wf"
    assert payload["argo_phase"] == "Failed"
    assert payload["failed_node_name"] == "train-mae"
    assert payload["error_exception"] == "ValueError: invalid feature"
    assert payload["error_code_location"] == "/tmp/model.py:17"
    assert payload["error_call_stack"] == ["/tmp/model.py:17", "/tmp/train.py:61"]


def test_risk_model_workflow_errors_endpoint_falls_back_when_workflow_missing(tmp_path) -> None:
    client = build_backtest_client(tmp_path)
    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id="g1",
            status="failed",
            argo_namespace="ns",
            argo_workflow_name="wf",
            params_json={},
            artifact_dir=str(tmp_path / "risk-artifacts" / "g1"),
            summary_metrics_json=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
    session.close()

    client.app.state.deps.risk_models._argo_submitter.get_workflow = lambda workflow_name, *, namespace=None: None  # type: ignore[assignment]

    response = client.get("/risk-models/g1/workflow-errors")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is False
    assert payload["status_message"] == "Workflow not found in Argo."
    assert payload["error_call_stack"] == []
