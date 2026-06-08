from __future__ import annotations

import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.terminal_command import format_terminal_command

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


@app.command(help="Print a copy-pasteable command line for Argo workflow submission logs.")
def main(
    command_line: str = typer.Option(..., "--command-line", help="Command line to print"),
    terminal_command_out: str = typer.Option(
        "/tmp/terminal-command.txt",
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    _write_text(terminal_command_out, format_terminal_command(sys.argv))
    typer.echo(command_line)


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
