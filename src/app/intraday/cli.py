from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import typer
import yaml

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.intraday.models import IntradayRunConfig
from app.intraday.pipeline import run_intraday_pipeline, write_intraday_artifacts

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def _load_config(path: str) -> IntradayRunConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("Intraday config root must be a mapping")
    if "intraday" in raw and isinstance(raw["intraday"], dict):
        raw = raw["intraday"]
    base_dir = config_path.parent.resolve()

    def _resolve_csv_path(source: dict[str, object]) -> None:
        data = source.get("data")
        if not isinstance(data, dict):
            return
        if data.get("type") != "csv":
            return
        path_value = data.get("path")
        if isinstance(path_value, str) and path_value and not Path(path_value).is_absolute():
            data["path"] = str((base_dir / path_value).resolve())

    universe = raw.get("universe")
    if isinstance(universe, dict):
        symbols = universe.get("symbols")
        if isinstance(symbols, list):
            for entry in symbols:
                if isinstance(entry, dict):
                    _resolve_csv_path(entry)
        benchmark = universe.get("benchmark")
        if isinstance(benchmark, dict):
            _resolve_csv_path(benchmark)
    return IntradayRunConfig.model_validate(raw)


@app.command(help="Run the intraday forecast pipeline and write JSON/parquet artifacts.")
def run(
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

    intraday_config = _load_config(config)
    target_output_dir = Path(output_dir or intraday_config.output_dir)
    result = run_intraday_pipeline(intraday_config, force_refresh=force_refresh)
    paths = write_intraday_artifacts(result, target_output_dir)

    path_map = {
        dataset_path_out: paths["dataset"],
        manifest_path_out: paths["manifest"],
        predictions_path_out: paths["predictions"],
        positions_path_out: paths["positions"],
        model_path_out: paths["model"],
        metrics_path_out: paths["metrics"],
    }
    for out_path, artifact_path in path_map.items():
        if out_path:
            _write_text(out_path, str(artifact_path))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
