from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.argo_template import load_yaml_template, patch_yaml_template

_TEMPLATE_PATH = Path(__file__).with_name("universe_workflow_template.yaml")


def _workflow_image() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_IMAGE", "backtest-app:latest")


def _workflow_service_account() -> str:
    return os.environ.get("ARGO_WORKFLOW_SERVICE_ACCOUNT", "backtest-workflow")


def _secret_name() -> str:
    return os.environ.get("BACKTEST_WORKFLOW_SECRET", "app-secrets")


def _command_line(parts: list[str]) -> str:
    import shlex

    return " ".join(shlex.quote(part) for part in parts)


def _base_spec(command_line: str) -> dict[str, Any]:
    template = load_yaml_template(_TEMPLATE_PATH)
    return patch_yaml_template(
        template,
        {
            "__WORKFLOW_IMAGE__": _workflow_image(),
            "__SERVICE_ACCOUNT__": _workflow_service_account(),
            "__SECRET_NAME__": _secret_name(),
            "__COMMAND_LINE__": command_line,
        },
    )


def build_symbol_universe_refresh_workflow_spec(*, universe_key: str | None, as_of: str) -> dict[str, Any]:
    key_arg = ["--key", universe_key] if universe_key else ["--all"]
    cmdline = _command_line(["kalyxctl", "universes", "refresh", *key_arg, "--as-of", as_of])
    return _base_spec(cmdline)


def build_symbol_universe_registry_sync_workflow_spec() -> dict[str, Any]:
    cmdline = _command_line(["kalyxctl", "universes", "sync-registry"])
    return _base_spec(cmdline)
