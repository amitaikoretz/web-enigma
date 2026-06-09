from __future__ import annotations

import base64
import shlex
import sys
from pathlib import Path

import typer

from app.backtests.argo_workflow import workflow_results_mount
from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.cli import _cmd_plan_shards
from app.script_logging import emit_error, emit_terminal_command

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _maybe_read_at_file(value: str) -> str:
    value = value.strip()
    if not value.startswith("@"):
        return value
    at_path = value[1:].strip()
    if not at_path:
        raise ValueError("empty @file reference")
    return Path(at_path).read_text(encoding="utf-8").strip()


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def _resolve_work_dir(backtest_id: str | None) -> Path:
    if backtest_id and backtest_id.strip():
        return Path(workflow_results_mount()) / backtest_id.strip()
    return Path("/workspace")


@app.command(help="Argo-safe wrapper around `kalyxctl plan-shards` without `sh -c` scripts.")
def main(
    config_path: str = typer.Option(
        "",
        "--config-path",
        help="Config path on the shared backtest-results volume (used when --config-b64 is empty)",
    ),
    config_b64: str = typer.Option(
        "",
        "--config-b64",
        help="Base64-encoded config YAML (supports Argo @filename response files)",
    ),
    split_by: str = typer.Option("", "--split-by", help="Argo shard grouping"),
    backtest_id: str = typer.Option("", "--backtest-id", help="Backtest job id (optional)"),
    manifest_path_out: str = typer.Option(
        "/tmp/manifest-path.txt",
        "--manifest-path-out",
        help="Write the resolved manifest path to this file (for Argo output parameters)",
    ),
    work_dir_out: str = typer.Option(
        "/tmp/work-dir.txt",
        "--work-dir-out",
        help="Write the resolved work dir to this file (for Argo output parameters)",
    ),
    shards_param_out: str = typer.Option(
        "/tmp/shards-param.json",
        "--shards-param-out",
        help="Write the shards param JSON array to this file (for Argo output parameters)",
    ),
    terminal_command_out: str = typer.Option(
        "/tmp/terminal-command.txt",
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="plan_shards_argo")

    resolved_backtest_id = backtest_id.strip() or None
    work_dir = _resolve_work_dir(resolved_backtest_id)
    work_dir.mkdir(parents=True, exist_ok=True)

    # Pre-create Argo output parameter files so emissary can always collect them,
    # even when shard planning fails early.
    manifest_path = work_dir / "manifest.json"
    _write_text(manifest_path_out, str(manifest_path))
    _write_text(work_dir_out, str(work_dir))
    _write_text(shards_param_out, "[]\n")

    resolved_config_b64 = config_b64.strip()
    if resolved_config_b64:
        try:
            raw_b64 = _maybe_read_at_file(resolved_config_b64)
            config_yaml = base64.b64decode(raw_b64, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError, OSError) as exc:
            emit_error("invalid-config-b64", f"Invalid --config-b64: {exc}", script="plan_shards_argo")
            raise typer.Exit(code=2) from exc
        config_file = work_dir / "config.yaml"
        config_file.write_text(config_yaml, encoding="utf-8")
    else:
        resolved_config_path = config_path.strip()
        if not resolved_config_path:
            emit_error(
                "missing-config-path",
                "Provide --config-path when --config-b64 is empty",
                script="plan_shards_argo",
            )
            raise typer.Exit(code=2)
        config_file = Path(resolved_config_path)

    rc = _cmd_plan_shards(
        str(config_file),
        str(work_dir),
        str(manifest_path),
        shards_param_out,
        split_by.strip() or None,
    )
    if rc != 0:
        raise typer.Exit(code=rc)


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
