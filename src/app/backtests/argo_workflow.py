from __future__ import annotations

import base64
import os
import textwrap
from typing import Any

WORKFLOW_TTL_SECONDS = 7 * 24 * 60 * 60
DEFAULT_WORKFLOW_RESULTS_MOUNT = "/data/backtest-results"
WORKFLOW_RETRY_LIMIT = 3
WORKFLOW_RETRY_MEMORY_TIERS = ("4Gi", "8Gi", "16Gi", "32Gi")


def workflow_results_mount() -> str:
    """Path where workflow pods mount the backtest-results PVC."""
    return os.environ.get("BACKTEST_WORKFLOW_RESULTS_MOUNT", DEFAULT_WORKFLOW_RESULTS_MOUNT).rstrip("/")


def workflow_artifact_paths(backtest_id: str) -> tuple[str, str]:
    base = workflow_results_mount()
    work_dir = f"{base}/{backtest_id}"
    return f"{work_dir}/{backtest_id}.yaml", f"{work_dir}/{backtest_id}.json"


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


def _api_base_url() -> str:
    return os.environ.get("BACKTEST_API_BASE_URL", "http://api.backtest.svc.cluster.local:8000")


def _volume_mounts(*, include_cache: bool = False) -> list[dict[str, str]]:
    mounts = [
        {"name": "workspace", "mountPath": "/workspace"},
        {"name": "backtest-results", "mountPath": workflow_results_mount()},
    ]
    if include_cache:
        mounts.append({"name": "backtest-cache", "mountPath": "/data/cache"})
    return mounts


def _container_env() -> list[dict[str, Any]]:
    return [{"secretRef": {"name": _secret_name()}}]


def _step_parameters(pairs: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "parameters": [{"name": name, "value": value} for name, value in pairs],
    }


def _retry_strategy() -> dict[str, Any]:
    return {
        "limit": WORKFLOW_RETRY_LIMIT,
        "retryPolicy": "Always",
    }


def _memory_retry_pod_spec_patch() -> str:
    memory_expr = " : ".join(
        [
            f"retries == {index} ? '{memory}'"
            for index, memory in enumerate(WORKFLOW_RETRY_MEMORY_TIERS[:-1])
        ]
        + [f"'{WORKFLOW_RETRY_MEMORY_TIERS[-1]}'"]
    )
    return textwrap.dedent(
        f"""\
        containers:
          - name: main
            resources:
              requests:
                memory: "{{{{={memory_expr}}}}}"
              limits:
                memory: "{{{{={memory_expr}}}}}"
        """
    )


def _print_payload_template() -> dict[str, Any]:
    return {
        "name": "print-payload",
        "retryStrategy": _retry_strategy(),
        "podSpecPatch": _memory_retry_pod_spec_patch(),
        "inputs": {
            "parameters": [
                {"name": "api-base-url"},
                {"name": "config-path"},
                {"name": "config-b64"},
                {"name": "split-by"},
                {"name": "backtest-id"},
                {"name": "output-path"},
            ]
        },
        "container": {
            "image": _workflow_image(),
            "imagePullPolicy": "IfNotPresent",
            "command": ["python", "-m", "app.standalone.print_argo_payload"],
            "args": [
                "--terminal-command-out",
                "/tmp/terminal-command.txt",
                "--api-base-url",
                "{{inputs.parameters.api-base-url}}",
                "--config-path",
                "{{inputs.parameters.config-path}}",
                "--config-b64",
                "{{inputs.parameters.config-b64}}",
                "--split-by",
                "{{inputs.parameters.split-by}}",
                "--backtest-id",
                "{{inputs.parameters.backtest-id}}",
                "--launch-curl-out",
                "/tmp/launch-curl.txt",
            ],
            "envFrom": _container_env(),
            "volumeMounts": _volume_mounts(),
        },
        "outputs": {
            "parameters": [
                {
                    "name": "launch-curl",
                    "valueFrom": {"path": "/tmp/launch-curl.txt"},
                }
                ,
                {
                    "name": "terminal-command",
                    "valueFrom": {"path": "/tmp/terminal-command.txt"},
                },
            ]
        },
    }


def _plan_shards_template() -> dict[str, Any]:
    return {
        "name": "plan-shards",
        "retryStrategy": _retry_strategy(),
        "podSpecPatch": _memory_retry_pod_spec_patch(),
        "inputs": {
            "parameters": [
                {"name": "config-path"},
                {"name": "config-b64"},
                {"name": "split-by"},
                {"name": "backtest-id"},
            ]
        },
        "container": {
            "image": _workflow_image(),
            "imagePullPolicy": "IfNotPresent",
            "command": ["python", "-m", "app.standalone.plan_shards_argo"],
            "args": [
                "--terminal-command-out",
                "/tmp/terminal-command.txt",
                "--config-path",
                "{{inputs.parameters.config-path}}",
                "--config-b64",
                "{{inputs.parameters.config-b64}}",
                "--split-by",
                "{{inputs.parameters.split-by}}",
                "--backtest-id",
                "{{inputs.parameters.backtest-id}}",
                "--manifest-path-out",
                "/tmp/manifest-path.txt",
                "--work-dir-out",
                "/tmp/work-dir.txt",
                "--shards-param-out",
                "/tmp/shards-param.json",
            ],
            "envFrom": _container_env(),
            "volumeMounts": _volume_mounts(),
        },
        "outputs": {
            "parameters": [
                {
                    "name": "shards",
                    "valueFrom": {"path": "/tmp/shards-param.json"},
                },
                {
                    "name": "manifest-path",
                    "valueFrom": {"path": "/tmp/manifest-path.txt"},
                },
                {
                    "name": "work-dir",
                    "valueFrom": {"path": "/tmp/work-dir.txt"},
                },
                {
                    "name": "terminal-command",
                    "valueFrom": {"path": "/tmp/terminal-command.txt"},
                },
            ]
        },
    }


def _run_shard_template() -> dict[str, Any]:
    return {
        "name": "run-shard",
        "metadata": {
            "annotations": {
                "workflows.argoproj.io/progress": "0/100",
            },
        },
        "retryStrategy": _retry_strategy(),
        "podSpecPatch": _memory_retry_pod_spec_patch(),
        "inputs": {
            "parameters": [
                {"name": "shard-id"},
                {"name": "shard-config-path"},
                {"name": "shard-output-path"},
            ]
        },
        "container": {
            "image": _workflow_image(),
            "imagePullPolicy": "IfNotPresent",
            "command": ["python", "-m", "app.standalone.run_shard_argo"],
            "args": [
                "--terminal-command-out",
                "/tmp/terminal-command.txt",
                "--shard-id",
                "{{inputs.parameters.shard-id}}",
                "--config",
                "{{inputs.parameters.shard-config-path}}",
                "--output",
                "{{inputs.parameters.shard-output-path}}",
                "--cache-dir",
                "/data/cache",
                "--shard-output-path-out",
                "/tmp/shard-output-path.txt",
            ],
            "envFrom": _container_env(),
            "volumeMounts": _volume_mounts(include_cache=True),
        },
        "outputs": {
            "parameters": [
                {
                    "name": "shard-output-path",
                    "valueFrom": {"path": "/tmp/shard-output-path.txt"},
                }
                ,
                {
                    "name": "terminal-command",
                    "valueFrom": {"path": "/tmp/terminal-command.txt"},
                },
            ]
        },
    }


def _merge_reports_template() -> dict[str, Any]:
    return {
        "name": "merge-reports",
        "retryStrategy": _retry_strategy(),
        "podSpecPatch": _memory_retry_pod_spec_patch(),
        "inputs": {
            "parameters": [
                {"name": "manifest-path"},
                {"name": "output-path"},
                {"name": "backtest-id"},
            ]
        },
        "container": {
            "image": _workflow_image(),
            "imagePullPolicy": "IfNotPresent",
            "command": ["python", "-m", "app.standalone.merge_reports_argo"],
            "args": [
                "--terminal-command-out",
                "/tmp/terminal-command.txt",
                "--manifest",
                "{{inputs.parameters.manifest-path}}",
                "--output",
                "{{inputs.parameters.output-path}}",
                "--backtest-id",
                "{{inputs.parameters.backtest-id}}",
                "--merged-output-path-out",
                "/tmp/merged-output-path.txt",
            ],
            "envFrom": _container_env(),
            "volumeMounts": _volume_mounts(),
        },
        "outputs": {
            "parameters": [
                {
                    "name": "output-path",
                    "valueFrom": {"path": "/tmp/merged-output-path.txt"},
                }
                ,
                {
                    "name": "terminal-command",
                    "valueFrom": {"path": "/tmp/terminal-command.txt"},
                },
            ]
        },
    }


def _backtest_batch_steps() -> list[list[dict[str, Any]]]:
    return [
        [
            {
                "name": "print-payload",
                "template": "print-payload",
                "arguments": _step_parameters(
                    [
                        ("api-base-url", "{{workflow.parameters.api-base-url}}"),
                        ("config-path", "{{workflow.parameters.config-path}}"),
                        ("config-b64", "{{workflow.parameters.config-b64}}"),
                        ("split-by", "{{workflow.parameters.split-by}}"),
                        ("backtest-id", "{{workflow.parameters.backtest-id}}"),
                        ("output-path", "{{workflow.parameters.output-path}}"),
                    ]
                ),
            }
        ],
        [
            {
                "name": "plan",
                "template": "plan-shards",
                "arguments": _step_parameters(
                    [
                        ("config-path", "{{workflow.parameters.config-path}}"),
                        ("config-b64", "{{workflow.parameters.config-b64}}"),
                        ("split-by", "{{workflow.parameters.split-by}}"),
                        ("backtest-id", "{{workflow.parameters.backtest-id}}"),
                    ]
                ),
            }
        ],
        [
            {
                "name": "run-shards",
                "template": "run-shard",
                "arguments": {
                    "parameters": [
                        {
                            "name": "shard-id",
                            "value": "{{item.shard_id}}",
                        },
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
        [
            {
                "name": "merge",
                "template": "merge-reports",
                "arguments": _step_parameters(
                    [
                        (
                            "manifest-path",
                            "{{steps.plan.outputs.parameters.manifest-path}}",
                        ),
                        ("output-path", "{{workflow.parameters.output-path}}"),
                        ("backtest-id", "{{workflow.parameters.backtest-id}}"),
                    ]
                ),
            }
        ],
    ]


def build_backtest_workflow_spec(
    *,
    config_path: str,
    output_path: str,
    split_by: str,
    backtest_id: str,
    config_yaml: str | None = None,
    api_base_url: str | None = None,
    shard_parallelism: int = 8,
) -> dict[str, Any]:
    parameters: list[dict[str, str]] = [
        {"name": "api-base-url", "value": api_base_url or _api_base_url()},
        {"name": "config-path", "value": config_path},
        {"name": "output-path", "value": output_path},
        {"name": "split-by", "value": split_by},
        {"name": "backtest-id", "value": backtest_id},
        {
            "name": "config-b64",
            "value": base64.b64encode(config_yaml.encode()).decode() if config_yaml else "",
        },
        {"name": "shard-parallelism", "value": str(shard_parallelism)},
    ]
    return {
        "entrypoint": "backtest-batch",
        "serviceAccountName": _workflow_service_account(),
        "parallelism": shard_parallelism,
        "ttlStrategy": {"secondsAfterCompletion": WORKFLOW_TTL_SECONDS},
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
                "steps": _backtest_batch_steps(),
            },
            _print_payload_template(),
            _plan_shards_template(),
            _run_shard_template(),
            _merge_reports_template(),
        ],
    }
