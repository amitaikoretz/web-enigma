from __future__ import annotations

import os
from typing import Any

from app.scans.models import ScanType


def build_scan_workflow_spec(
    *,
    scan_type: ScanType,
    scan_id: str,
    results_path: str,
    params_json: str,
) -> dict[str, Any]:
    """
    Build a Workflow spec for a scan run.

    Notes:
    - We write output parameters to /tmp (not a mounted PVC) because emissary executor
      can be unreliable reading output parameters from workflow volume mounts.
    - results_path is on the shared results PVC (same pattern as backtests).
    """
    api_base_url = os.environ.get("BACKTEST_API_BASE_URL", "").strip() or None
    if api_base_url is None:
        api_base_url = "http://backtest-api.backtest.svc.cluster.local:8000"
    return {
        "serviceAccountName": os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow"),
        "entrypoint": "scan",
        "ttlStrategy": {"secondsAfterCompletion": 604800},
        "arguments": {
            "parameters": [
                {"name": "scan-id", "value": scan_id},
                {"name": "scan-type", "value": scan_type},
                {"name": "results-path", "value": results_path},
                {"name": "params-json", "value": params_json},
                {"name": "api-base-url", "value": api_base_url},
            ]
        },
        "volumes": [
            {
                "name": "backtest-results",
                "persistentVolumeClaim": {"claimName": "backtest-results"},
            }
        ],
        "templates": [
            {
                "name": "scan",
                "inputs": {
                    "parameters": [
                        {"name": "scan-id"},
                        {"name": "scan-type"},
                        {"name": "results-path"},
                        {"name": "params-json"},
                    ]
                },
                "container": {
                    "image": "backtest-app:latest",
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["python", "-m", f"app.standalone.run_scan_{scan_type}_argo"],
                    "args": [
                        "--terminal-command-out",
                        "/tmp/terminal-command.txt",
                        "--scan-id",
                        "{{inputs.parameters.scan-id}}",
                        "--results-path",
                        "{{inputs.parameters.results-path}}",
                        "--params-json",
                        "{{inputs.parameters.params-json}}",
                    ],
                    "envFrom": [{"secretRef": {"name": "app-secrets"}}],
                    "volumeMounts": [{"name": "backtest-results", "mountPath": "/data/backtest-results"}],
                },
                "outputs": {
                    "parameters": [
                        {"name": "terminal-command", "valueFrom": {"path": "/tmp/terminal-command.txt"}},
                        {"name": "error-exception", "valueFrom": {"path": "/tmp/error-exception.txt"}},
                        {"name": "error-code-location", "valueFrom": {"path": "/tmp/error-code-location.txt"}},
                        {"name": "error-call-stack", "valueFrom": {"path": "/tmp/error-call-stack.txt"}},
                        {"name": "error-traceback", "valueFrom": {"path": "/tmp/error-traceback.txt"}},
                    ]
                },
            }
        ],
    }
