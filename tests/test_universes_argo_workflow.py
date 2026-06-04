from __future__ import annotations

from app.universes.argo_workflow import (
    build_symbol_universe_registry_sync_workflow_spec,
    build_symbol_universe_refresh_workflow_spec,
)


def _output_names(spec: dict[str, object], template_name: str) -> set[str]:
    for template in spec.get("templates", []):  # type: ignore[union-attr]
        if isinstance(template, dict) and template.get("name") == template_name:
            outputs = template.get("outputs", {})
            if isinstance(outputs, dict):
                params = outputs.get("parameters", [])
                return {
                    item.get("name")
                    for item in params
                    if isinstance(item, dict) and isinstance(item.get("name"), str)
                }
    raise AssertionError(f"template {template_name!r} not found")


def test_universe_refresh_workflow_uses_terminal_command_output() -> None:
    spec = build_symbol_universe_refresh_workflow_spec(universe_key="abc", as_of="2026-06-01")

    names = _output_names(spec, "refresh")
    assert "terminal-command" in names
    assert "commandLine" not in names


def test_universe_registry_sync_workflow_uses_terminal_command_output() -> None:
    spec = build_symbol_universe_registry_sync_workflow_spec()

    names = _output_names(spec, "sync-registry")
    assert "terminal-command" in names
    assert "commandLine" not in names
