from __future__ import annotations

import shlex
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Argo-safe wrapper for the intraday forecast pipeline.")
def main(
    config: str = typer.Option(..., "--config", help="Intraday YAML config path"),
    output_dir: str | None = typer.Option(None, "--output-dir", help="Directory for generated artifacts"),
    dataset_path_out: str | None = typer.Option(None, "--dataset-path-out", help="Write dataset parquet path here"),
    manifest_path_out: str | None = typer.Option(None, "--manifest-path-out", help="Write manifest JSON path here"),
    predictions_path_out: str | None = typer.Option(None, "--predictions-path-out", help="Write predictions parquet path here"),
    positions_path_out: str | None = typer.Option(None, "--positions-path-out", help="Write positions parquet path here"),
    model_path_out: str | None = typer.Option(None, "--model-path-out", help="Write model JSON path here"),
    metrics_path_out: str | None = typer.Option(None, "--metrics-path-out", help="Write metrics JSON path here"),
    terminal_command_out: str | None = typer.Option(
        None,
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
    force_refresh: bool = typer.Option(False, "--force-refresh", help="Bypass cached market-data downloads"),
) -> None:
    _write_text(terminal_command_out, _terminal_command(sys.argv))
    for path in [dataset_path_out, manifest_path_out, predictions_path_out, positions_path_out, model_path_out, metrics_path_out]:
        _write_text(path, "")

    from app.intraday.cli import run as intraday_run

    intraday_run(
        config=config,
        output_dir=output_dir,
        dataset_path_out=dataset_path_out,
        manifest_path_out=manifest_path_out,
        predictions_path_out=predictions_path_out,
        positions_path_out=positions_path_out,
        model_path_out=model_path_out,
        metrics_path_out=metrics_path_out,
        terminal_command_out=terminal_command_out,
        force_refresh=force_refresh,
    )


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
