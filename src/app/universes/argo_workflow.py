from __future__ import annotations

import os
from typing import Any

WORKFLOW_TTL_SECONDS = 7 * 24 * 60 * 60


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _secret_name() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_SECRET", "app-secrets")


def _container_env() -> list[dict[str, Any]]:
    return [{"secretRef": {"name": _secret_name()}}]


def build_symbol_universe_refresh_workflow_spec(*, universe_key: str | None, as_of: str) -> dict[str, Any]:
    key_arg = ["--key", universe_key] if universe_key else ["--all"]
    cmdline = " ".join(["kalyxctl", "universes", "refresh", *key_arg, "--as-of", as_of])
    return {
        "serviceAccountName": _workflow_service_account(),
        "ttlStrategy": {"secondsAfterCompletion": WORKFLOW_TTL_SECONDS},
        "entrypoint": "refresh",
        "templates": [
            {
                "name": "refresh",
                "container": {
                    "image": _workflow_image(),
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["sh", "-c"],
                    "args": [f"printf '%s\\n' {cmdline!r} > /tmp/argo-command-line.txt; exec {cmdline}"],
                    "envFrom": _container_env(),
                },
                "outputs": {
                    "parameters": [
                        {
                            "name": "commandLine",
                            "valueFrom": {"path": "/tmp/argo-command-line.txt"},
                        }
                    ]
                },
            }
        ],
    }


def build_symbol_universe_registry_sync_workflow_spec() -> dict[str, Any]:
    cmdline = " ".join(["kalyxctl", "universes", "sync-registry"])
    return {
        "serviceAccountName": _workflow_service_account(),
        "ttlStrategy": {"secondsAfterCompletion": WORKFLOW_TTL_SECONDS},
        "entrypoint": "sync-registry",
        "templates": [
            {
                "name": "sync-registry",
                "container": {
                    "image": _workflow_image(),
                    "imagePullPolicy": "IfNotPresent",
                    "command": ["sh", "-c"],
                    "args": [f"printf '%s\\n' {cmdline!r} > /tmp/argo-command-line.txt; exec {cmdline}"],
                    "envFrom": _container_env(),
                },
                "outputs": {
                    "parameters": [
                        {
                            "name": "commandLine",
                            "valueFrom": {"path": "/tmp/argo-command-line.txt"},
                        }
                    ]
                },
            }
        ],
    }
