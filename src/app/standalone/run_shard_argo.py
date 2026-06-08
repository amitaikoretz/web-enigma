from __future__ import annotations

import shlex
import sys
from pathlib import Path

import typer

from app.cli import _cmd_run
from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Argo-safe wrapper around `kalyxctl run` without `sh -c` scripts.")
def main(
    shard_id: str = typer.Option("", "--shard-id", help="Shard id (for logging only)"),
    config_path: str = typer.Option(..., "--config", help="Shard config path"),
    output_path: str = typer.Option(..., "--output", help="Shard output path"),
    cache_dir: str = typer.Option("/data/cache", "--cache-dir", help="Cache directory"),
    shard_output_path_out: str = typer.Option(
        "/tmp/shard-output-path.txt",
        "--shard-output-path-out",
        help="Write the shard output path to this file (for Argo output parameters)",
    ),
    terminal_command_out: str = typer.Option(
        "/tmp/terminal-command.txt",
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    _write_text(terminal_command_out, _terminal_command(sys.argv))

    resolved_shard_id = shard_id.strip()
    if resolved_shard_id:
        typer.echo(f"Running shard {resolved_shard_id}")
    typer.echo(f"Shard config: {config_path}")
    typer.echo(f"Shard output: {output_path}")
    typer.echo(f"Cache dir: {cache_dir}")

    try:
        rc = _cmd_run(
            config_path=config_path,
            output_path=output_path,
            cache_dir=cache_dir,
            cache_refresh=False,
            no_cache=False,
            progress_file=None,
        )
        if rc != 0:
            raise typer.Exit(code=rc)
    finally:
        # Argo still needs this output parameter path even when the shard fails,
        # otherwise the executor logs a secondary "cannot save parameter" error.
        _write_text(shard_output_path_out, output_path)


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
