from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.daily_index_forecast.metrics import aggregate_nested_metrics
from app.daily_index_forecast.models import DailyIndexCostConfig, DailyIndexTrainConfig, DailyIndexWalkForwardConfig
from app.daily_index_forecast.pipeline import train_daily_index_model, write_json
from app.feature_importance.io import build_linear_feature_importance, write_feature_importance_artifact
from app.standalone.daily_index_common import json_default, write_text
from app.script_logging import emit_terminal_command

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command(help="Train and evaluate the Daily Index Forecast model (for Argo workflow).")
def main(
    group_id: str = typer.Option(..., "--group-id"),
    feature_run_id: str = typer.Option(..., "--feature-run-id"),
    dataset_path: str = typer.Option(..., "--dataset-path"),
    features_path: str = typer.Option(..., "--features-path"),
    labels_path: str = typer.Option(..., "--labels-path"),
    walk_forward_json: str = typer.Option(..., "--walk-forward-json"),
    train_config_json: str = typer.Option("{}", "--train-config-json"),
    costs_json: str = typer.Option(..., "--costs-json"),
    artifact_dir: str = typer.Option(..., "--artifact-dir"),
    model_path_out: str = typer.Option(..., "--model-path-out"),
    metrics_path_out: str = typer.Option(..., "--metrics-path-out"),
    terminal_command_out: str | None = typer.Option(None, "--terminal-command-out"),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="daily_index_train_evaluate_argo")
    for path in [model_path_out, metrics_path_out]:
        write_text(path, "")

    dataset = pd.read_parquet(dataset_path)
    walk_forward = DailyIndexWalkForwardConfig.model_validate(json.loads(walk_forward_json))
    train_config = DailyIndexTrainConfig.model_validate(json.loads(train_config_json or "{}"))
    costs = DailyIndexCostConfig.model_validate(json.loads(costs_json))

    feature_columns = [column for column in dataset.columns if column in {"bars_seen", "opening_window_minutes"}]
    artifact, metrics, _ = train_daily_index_model(
        dataset,
        group_id=group_id,
        feature_run_id=feature_run_id,
        train_config=train_config,
        walk_forward=walk_forward,
        costs=costs,
        feature_columns=[col for col in dataset.columns if col not in {"symbol", "session_date", "decision_time", "decision_timestamp", "session_open_timestamp", "session_close_timestamp", "feature_quality_flag", "exit_timestamp", "label_quality_flag", "positive_after_cost", "return_to_close_pct", "return_to_close_bps", "net_return_after_cost_bps", "entry_price", "exit_price", "intraday_max_runup_bps", "intraday_max_drawdown_bps", "post_decision_realized_volatility_bps", "open_price", "high_price", "low_price", "last_price", "volume_so_far", "dollar_volume_so_far"}],
    )

    model_path = Path(artifact_dir) / "model.json"
    metrics_path = Path(artifact_dir) / "metrics.json"
    feature_importance_path = Path(artifact_dir) / "feature_importance.json"
    write_json(model_path, artifact.model_dump(mode="json"))
    write_json(metrics_path, metrics.model_dump(mode="json"))
    write_feature_importance_artifact(
        feature_importance_path,
        build_linear_feature_importance(
            target_key="daily_index_forecast",
            feature_names=artifact.selected_features,
            coefficients=artifact.coefficients,
            source="daily_index_forecast:model.json",
            metadata={"group_id": group_id, "feature_run_id": feature_run_id, "selected_alpha": artifact.selected_alpha},
        ),
    )
    write_text(model_path_out, str(model_path))
    write_text(metrics_path_out, str(metrics_path))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
