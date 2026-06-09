from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.script_logging import emit_terminal_command
from app.scans.params import TrendScanParams

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Run the trend scanner and write results.json for Argo collection.")
def main(
    scan_id: str = typer.Option(..., "--scan-id", help="Scan run id"),
    results_path: str = typer.Option(..., "--results-path", help="Write results JSON to this path"),
    params_json: str = typer.Option("{}", "--params-json", help="Scanner parameters JSON"),
    terminal_command_out: str = typer.Option(
        "/tmp/terminal-command.txt",
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="run_scan_trend_argo")

    raw_params = json.loads(params_json or "{}")
    params = TrendScanParams.model_validate(raw_params).model_dump()
    payload = {
        "scan_id": scan_id,
        "scan_type": "trend",
        "params": params,
        "results": [],
        "note": "Scanner implementation pending; this is a placeholder results schema.",
    }
    path = Path(results_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
