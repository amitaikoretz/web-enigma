from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.strategies.exit_rules import ExitRulesSelection
from app.strategies.triggers import TriggerSelection


def _load_yaml_object(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be an object: {path}")
    return data


def resolve_config_ref(path: str, *, base_dir: Path) -> Path:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = base_dir / resolved
    return resolved.resolve()


def load_trigger_selection(path: str, *, base_dir: Path) -> TriggerSelection:
    resolved = resolve_config_ref(path, base_dir=base_dir)
    return TriggerSelection.model_validate(_load_yaml_object(resolved))


def load_exit_rules_selection(path: str, *, base_dir: Path) -> ExitRulesSelection:
    resolved = resolve_config_ref(path, base_dir=base_dir)
    return ExitRulesSelection.model_validate(_load_yaml_object(resolved))

