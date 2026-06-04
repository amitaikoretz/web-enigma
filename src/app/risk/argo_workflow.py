from __future__ import annotations

import os
from typing import Any

from app.backtests.argo_workflow import (
    WORKFLOW_TTL_SECONDS,
    _container_env,  # re-use secret envFrom
    _volume_mounts,
    workflow_results_mount,
)


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _results_claim_name() -> str:
    return os.environ.get("BACKTEST_RESULTS_CLAIM", "backtest-results")


def _cache_claim_name() -> str:
    return os.environ.get("BACKTEST_CACHE_CLAIM", "backtest-cache")


def _step_parameters(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    return {"parameters": [{"name": name, "value": value} for name, value in pairs]}


def _error_output_parameters(tmp_dir: str = "/tmp") -> list[dict[str, Any]]:
    base = tmp_dir.rstrip("/")
    return [
        {"name": "error-exception", "valueFrom": {"path": f"{base}/error-exception.txt"}},
        {"name": "error-code-location", "valueFrom": {"path": f"{base}/error-code-location.txt"}},
        {"name": "error-call-stack", "valueFrom": {"path": f"{base}/error-call-stack.txt"}},
        {"name": "error-traceback", "valueFrom": {"path": f"{base}/error-traceback.txt"}},
    ]


def _terminal_command_output_parameter(path: str = "/tmp/terminal-command.txt") -> dict[str, Any]:
    return {"name": "terminal-command", "valueFrom": {"path": path}}


def _build_dataset_template() -> dict[str, Any]:
    return {
        "name": "build-dataset",
        "inputs": {
            "parameters": [
                {"name": "group-id"},
                {"name": "backtest-ids-json"},
                {"name": "dataset-config-json"},
                {"name": "artifact-dir"},
            ]
        },
        "container": {
            "image": _workflow_image(),
            "imagePullPolicy": "IfNotPresent",
            "command": ["python", "-m", "app.standalone.risk_build_dataset_argo"],
            "args": [
                "--terminal-command-out",
                "/tmp/terminal-command.txt",
                "--group-id",
                "{{inputs.parameters.group-id}}",
                "--backtest-ids-json",
                "{{inputs.parameters.backtest-ids-json}}",
                "--dataset-config-json",
                "{{inputs.parameters.dataset-config-json}}",
                "--artifact-dir",
                "{{inputs.parameters.artifact-dir}}",
                "--dataset-path-out",
                "/tmp/dataset-path.txt",
                "--manifest-path-out",
                "/tmp/manifest-path.txt",
                "--feature-cols-out",
                "/tmp/feature-cols.json",
            ],
            "envFrom": _container_env(),
            "volumeMounts": _volume_mounts(include_cache=True),
        },
        "outputs": {
            "parameters": [
                {"name": "dataset-path", "valueFrom": {"path": "/tmp/dataset-path.txt"}},
                {"name": "manifest-path", "valueFrom": {"path": "/tmp/manifest-path.txt"}},
                {"name": "feature-cols", "valueFrom": {"path": "/tmp/feature-cols.json"}},
                _terminal_command_output_parameter(),
            ]
            + _error_output_parameters(),
        },
    }


def _train_target_template(*, name: str, module: str) -> dict[str, Any]:
    return {
        "name": name,
        "inputs": {
            "parameters": [
                {"name": "group-id"},
                {"name": "dataset-path"},
                {"name": "manifest-path"},
                {"name": "feature-cols"},
                {"name": "train-config-json"},
                {"name": "artifact-dir"},
            ]
        },
        "container": {
            "image": _workflow_image(),
            "imagePullPolicy": "IfNotPresent",
            "command": ["python", "-m", module],
            "args": [
                "--terminal-command-out",
                "/tmp/terminal-command.txt",
                "--group-id",
                "{{inputs.parameters.group-id}}",
                "--dataset-path",
                "{{inputs.parameters.dataset-path}}",
                "--manifest-path",
                "{{inputs.parameters.manifest-path}}",
                "--feature-cols-json",
                "{{inputs.parameters.feature-cols}}",
                "--train-config-json",
                "{{inputs.parameters.train-config-json}}",
                "--artifact-dir",
                "{{inputs.parameters.artifact-dir}}",
                "--model-path-out",
                "/tmp/model-path.txt",
                "--metrics-path-out",
                "/tmp/metrics-path.txt",
            ],
            "envFrom": _container_env(),
            "volumeMounts": _volume_mounts(include_cache=True),
        },
        "outputs": {
            "parameters": [
                {"name": "model-path", "valueFrom": {"path": "/tmp/model-path.txt"}},
                {"name": "metrics-path", "valueFrom": {"path": "/tmp/metrics-path.txt"}},
                _terminal_command_output_parameter(),
            ]
            + _error_output_parameters(),
        },
    }


def _register_results_template() -> dict[str, Any]:
    return {
        "name": "register-results",
        "inputs": {
            "parameters": [
                {"name": "group-id"},
                {"name": "family"},
                {"name": "manifest-path"},
                {"name": "feature-cols"},
                {"name": "stop-model-path"},
                {"name": "stop-metrics-path"},
                {"name": "mae-model-path"},
                {"name": "mae-metrics-path"},
            ]
        },
        "container": {
            "image": _workflow_image(),
            "imagePullPolicy": "IfNotPresent",
            "command": ["python", "-m", "app.standalone.risk_register_results_argo"],
            "args": [
                "--terminal-command-out",
                "/tmp/terminal-command.txt",
                "--group-id",
                "{{inputs.parameters.group-id}}",
                "--family",
                "{{inputs.parameters.family}}",
                "--manifest-path",
                "{{inputs.parameters.manifest-path}}",
                "--feature-cols-json",
                "{{inputs.parameters.feature-cols}}",
                "--stop-model-path",
                "{{inputs.parameters.stop-model-path}}",
                "--stop-metrics-path",
                "{{inputs.parameters.stop-metrics-path}}",
                "--mae-model-path",
                "{{inputs.parameters.mae-model-path}}",
                "--mae-metrics-path",
                "{{inputs.parameters.mae-metrics-path}}",
            ],
            "envFrom": _container_env(),
            "volumeMounts": _volume_mounts(),
        },
        "outputs": {
            "parameters": [_terminal_command_output_parameter()] + _error_output_parameters(),
        },
    }


def build_risk_model_workflow_spec(
    *,
    group_id: str,
    family: str,
    backtest_ids_json: str,
    dataset_config_json: str,
    train_config_json: str,
    artifact_dir: str,
) -> dict[str, Any]:
    return {
        "serviceAccountName": _workflow_service_account(),
        "ttlStrategy": {"secondsAfterCompletion": WORKFLOW_TTL_SECONDS},
        "entrypoint": "main",
        "volumes": [
            {"name": "workspace", "emptyDir": {}},
            {"name": "backtest-results", "persistentVolumeClaim": {"claimName": _results_claim_name()}},
            {"name": "backtest-cache", "persistentVolumeClaim": {"claimName": _cache_claim_name()}},
        ],
        "templates": [
            {
                "name": "main",
                "inputs": {
                    "parameters": [
                        {"name": "group-id"},
                        {"name": "backtest-ids-json"},
                        {"name": "dataset-config-json"},
                        {"name": "train-config-json"},
                        {"name": "artifact-dir"},
                        {"name": "family"},
                    ]
                },
                "steps": [
                    [
                        {
                            "name": "build-dataset",
                            "template": "build-dataset",
                            "arguments": _step_parameters(
                                [
                                    ("group-id", "{{inputs.parameters.group-id}}"),
                                    ("backtest-ids-json", "{{inputs.parameters.backtest-ids-json}}"),
                                    ("dataset-config-json", "{{inputs.parameters.dataset-config-json}}"),
                                    ("artifact-dir", "{{inputs.parameters.artifact-dir}}"),
                                ]
                            ),
                        }
                    ],
                    [
                        {
                            "name": "train-stop",
                            "template": "train-stop",
                            "arguments": _step_parameters(
                                [
                                    ("group-id", "{{inputs.parameters.group-id}}"),
                                    ("dataset-path", "{{steps.build-dataset.outputs.parameters.dataset-path}}"),
                                    ("manifest-path", "{{steps.build-dataset.outputs.parameters.manifest-path}}"),
                                    ("feature-cols", "{{steps.build-dataset.outputs.parameters.feature-cols}}"),
                                    ("train-config-json", "{{inputs.parameters.train-config-json}}"),
                                    ("artifact-dir", "{{inputs.parameters.artifact-dir}}"),
                                ]
                            ),
                        }
                    ],
                    [
                        {
                            "name": "train-mae",
                            "template": "train-mae",
                            "arguments": _step_parameters(
                                [
                                    ("group-id", "{{inputs.parameters.group-id}}"),
                                    ("dataset-path", "{{steps.build-dataset.outputs.parameters.dataset-path}}"),
                                    ("manifest-path", "{{steps.build-dataset.outputs.parameters.manifest-path}}"),
                                    ("feature-cols", "{{steps.build-dataset.outputs.parameters.feature-cols}}"),
                                    ("train-config-json", "{{inputs.parameters.train-config-json}}"),
                                    ("artifact-dir", "{{inputs.parameters.artifact-dir}}"),
                                ]
                            ),
                        }
                    ],
                    [
                        {
                            "name": "register-results",
                            "template": "register-results",
                            "arguments": _step_parameters(
                                [
                                    ("group-id", "{{inputs.parameters.group-id}}"),
                                    ("manifest-path", "{{steps.build-dataset.outputs.parameters.manifest-path}}"),
                                    ("feature-cols", "{{steps.build-dataset.outputs.parameters.feature-cols}}"),
                                    ("stop-model-path", "{{steps.train-stop.outputs.parameters.model-path}}"),
                                    ("stop-metrics-path", "{{steps.train-stop.outputs.parameters.metrics-path}}"),
                                    ("mae-model-path", "{{steps.train-mae.outputs.parameters.model-path}}"),
                                    ("mae-metrics-path", "{{steps.train-mae.outputs.parameters.metrics-path}}"),
                                    ("family", "{{inputs.parameters.family}}"),
                                ]
                            ),
                        }
                    ],
                ],
            },
            _build_dataset_template(),
            _train_target_template(name="train-stop", module="app.standalone.risk_train_stop_argo"),
            _train_target_template(name="train-mae", module="app.standalone.risk_train_mae_argo"),
            _register_results_template(),
        ],
        "arguments": _step_parameters(
            [
                ("group-id", group_id),
                ("backtest-ids-json", backtest_ids_json),
                ("dataset-config-json", dataset_config_json),
                ("train-config-json", train_config_json),
                ("artifact-dir", artifact_dir),
                ("family", family),
            ]
        ),
    }
