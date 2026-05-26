from __future__ import annotations

import base64
import os
from typing import Any


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _results_claim_name() -> str:
    return os.environ.get("BACKTEST_RESULTS_CLAIM", "backtest-results")


def _cache_claim_name() -> str:
    return os.environ.get("BACKTEST_CACHE_CLAIM", "backtest-cache")


def _secret_name() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_SECRET", "app-secrets")


def _plan_shards_container(*, split_by_template: str) -> dict[str, Any]:
    # Stage config from an inline parameter when set; otherwise read config-path on the PVC.
    # shards-param goes to /tmp so Argo's wait sidecar can collect the output parameter
    # (paths on workflow volume mounts are skipped by the emissary executor).
    plan_script = "\n".join(
        [
            "set -e",
            'if [ -n "{{workflow.parameters.config-b64}}" ]; then',
            "  mkdir -p /workspace",
            '  echo "{{workflow.parameters.config-b64}}" | base64 -d > /workspace/config.yaml',
            "  CONFIG=/workspace/config.yaml",
            "else",
            '  CONFIG="{{workflow.parameters.config-path}}"',
            "fi",
            "exec backtest plan-shards \\",
            '  --config "$CONFIG" \\',
            "  --work-dir /workspace \\",
            "  --manifest /workspace/manifest.json \\",
            "  --shards-param /tmp/shards-param.json \\",
            f"  --split-by {split_by_template}",
        ]
    )
    return {
        "image": _workflow_image(),
        "imagePullPolicy": "IfNotPresent",
        "command": ["sh", "-c"],
        "args": [plan_script],
        "envFrom": [{"secretRef": {"name": _secret_name()}}],
        "volumeMounts": [
            {"name": "workspace", "mountPath": "/workspace"},
            {"name": "backtest-results", "mountPath": "/data/backtest-results"},
        ],
    }


def build_backtest_workflow_spec(
    *,
    config_path: str,
    output_path: str,
    split_by: str,
    backtest_id: str,
    config_yaml: str | None = None,
) -> dict[str, Any]:
    parameters: list[dict[str, str]] = [
        {"name": "config-path", "value": config_path},
        {"name": "output-path", "value": output_path},
        {"name": "split-by", "value": split_by},
        {"name": "backtest-id", "value": backtest_id},
        {
            "name": "config-b64",
            "value": base64.b64encode(config_yaml.encode()).decode() if config_yaml else "",
        },
    ]
    spec: dict[str, Any] = {
        "entrypoint": "backtest-batch",
        "serviceAccountName": _workflow_service_account(),
        "arguments": {
            "parameters": parameters,
        },
        "volumeClaimTemplates": [
            {
                "metadata": {"name": "workspace"},
                "spec": {
                    "accessModes": ["ReadWriteOnce"],
                    "resources": {"requests": {"storage": "5Gi"}},
                },
            }
        ],
        "volumes": [
            {
                "name": "backtest-results",
                "persistentVolumeClaim": {"claimName": _results_claim_name()},
            },
            {
                "name": "backtest-cache",
                "persistentVolumeClaim": {"claimName": _cache_claim_name()},
            },
        ],
        "templates": [
            {
                "name": "backtest-batch",
                "steps": [
                    [{"name": "plan", "template": "plan-shards"}],
                    [
                        {
                            "name": "run-shards",
                            "template": "run-shard",
                            "arguments": {
                                "parameters": [
                                    {
                                        "name": "shard-config-path",
                                        "value": "{{item.config_path}}",
                                    },
                                    {
                                        "name": "shard-output-path",
                                        "value": "{{item.output_path}}",
                                    },
                                ]
                            },
                            "withParam": "{{steps.plan.outputs.parameters.shards}}",
                        }
                    ],
                    [{"name": "merge", "template": "merge-reports"}],
                ],
            },
            {
                "name": "plan-shards",
                "container": _plan_shards_container(
                    split_by_template="{{workflow.parameters.split-by}}",
                ),
                "outputs": {
                    "parameters": [
                        {
                            "name": "shards",
                            "valueFrom": {"path": "/tmp/shards-param.json"},
                        }
                    ]
                },
            },
            {
                "name": "run-shard",
                "inputs": {
                    "parameters": [
                        {"name": "shard-config-path"},
                        {"name": "shard-output-path"},
                    ]
                },
                "container": {
                    "image": _workflow_image(),
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["backtest", "run"],
                    "args": [
                        "--config",
                        "{{inputs.parameters.shard-config-path}}",
                        "--output",
                        "{{inputs.parameters.shard-output-path}}",
                        "--cache-dir",
                        "/data/cache",
                    ],
                    "envFrom": [{"secretRef": {"name": _secret_name()}}],
                    "volumeMounts": [
                        {"name": "workspace", "mountPath": "/workspace"},
                        {"name": "backtest-cache", "mountPath": "/data/cache"},
                    ],
                },
            },
            {
                "name": "merge-reports",
                "container": {
                    "image": _workflow_image(),
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["backtest", "merge"],
                    "args": [
                        "--manifest",
                        "/workspace/manifest.json",
                        "--output",
                        "{{workflow.parameters.output-path}}",
                        "--backtest-id",
                        "{{workflow.parameters.backtest-id}}",
                    ],
                    "envFrom": [{"secretRef": {"name": _secret_name()}}],
                    "volumeMounts": [
                        {"name": "workspace", "mountPath": "/workspace"},
                        {"name": "backtest-results", "mountPath": "/data/backtest-results"},
                    ],
                },
            },
        ],
    }
    return spec
