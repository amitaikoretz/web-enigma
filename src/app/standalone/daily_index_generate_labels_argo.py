from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.config.models import DataCacheConfig
from app.daily_index_forecast.models import DailyIndexCostConfig, DailyIndexFeatureConfig, DailyIndexUniverseConfig
from app.daily_index_forecast.pipeline import build_dataset_frames, save_dataset_artifacts
from app.script_logging import emit_terminal_command

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command(help="Generate Daily Index Forecast labels (for Argo workflow).")
def main(
    group_id: str = typer.Option(..., "--group-id"),
    feature_run_id: str = typer.Option(..., "--feature-run-id"),
    universe_json: str = typer.Option(..., "--universe-json"),
    feature_config_json: str = typer.Option(..., "--feature-config-json"),
    costs_json: str = typer.Option(..., "--costs-json"),
    data_cache_json: str = typer.Option("{}", "--data-cache-json"),
    artifact_dir: str = typer.Option(..., "--artifact-dir"),
    labels_path_out: str = typer.Option(..., "--labels-path-out"),
    manifest_path_out: str = typer.Option(..., "--manifest-path-out"),
    terminal_command_out: str | None = typer.Option(None, "--terminal-command-out"),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="daily_index_generate_labels_argo")
    for path in [labels_path_out, manifest_path_out]:
        write_text(path, "")

    universe = DailyIndexUniverseConfig.model_validate(json.loads(universe_json))
    feature_config = DailyIndexFeatureConfig.model_validate(json.loads(feature_config_json))
    costs = DailyIndexCostConfig.model_validate(json.loads(costs_json))
    data_cache = DataCacheConfig.model_validate(json.loads(data_cache_json or "{}"))

    feature_df, label_df, joined_df, manifest, _ = build_dataset_frames(
        universe,
        feature_config,
        costs,
        data_cache,
    )
    _, _, labels_path, manifest_path = save_dataset_artifacts(
        output_dir=Path(artifact_dir),
        feature_df=feature_df,
        label_df=label_df,
        joined_df=joined_df,
        manifest=manifest,
    )
    write_text(labels_path_out, str(labels_path))
    write_text(manifest_path_out, str(manifest_path))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
