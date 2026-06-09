from __future__ import annotations

import shlex
import sys
from pathlib import Path

import typer

from app.cli import _cmd_merge
from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.script_logging import emit_terminal_command

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Argo-safe wrapper around `kalyxctl merge` without `sh -c` scripts.")
def main(
    manifest_path: str = typer.Option(..., "--manifest", help="Manifest JSON path"),
    output_path: str = typer.Option(..., "--output", help="Merged report output path"),
    backtest_id: str = typer.Option("", "--backtest-id", help="Backtest job id (optional)"),
    merged_output_path_out: str = typer.Option(
        "/tmp/merged-output-path.txt",
        "--merged-output-path-out",
        help="Write the merged output path to this file (for Argo output parameters)",
    ),
    terminal_command_out: str = typer.Option(
        "/tmp/terminal-command.txt",
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="merge_reports_argo")

    resolved_backtest_id = backtest_id.strip() or None
    rc = _cmd_merge(manifest_path=manifest_path, output_path=output_path, backtest_id=resolved_backtest_id)
    if rc != 0:
        raise typer.Exit(code=rc)

    _write_text(merged_output_path_out, output_path)


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
