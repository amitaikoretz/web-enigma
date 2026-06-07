from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.daily_index_forecast.models import DailyIndexForecastDatasetManifestSummary
from app.daily_index_forecast.persistence import SqlAlchemyDailyIndexForecastRepository
from app.db.session import get_session_factory
from app.standalone.daily_index_common import terminal_command, write_text

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.command(help="Register Daily Index Forecast artifacts and metrics in the DB (for Argo workflow).")
def main(
    group_id: str = typer.Option(..., "--group-id"),
    feature_run_id: str = typer.Option(..., "--feature-run-id"),
    manifest_path: str = typer.Option(..., "--manifest-path"),
    model_path: str = typer.Option(..., "--model-path"),
    metrics_path: str = typer.Option(..., "--metrics-path"),
    features_path: str = typer.Option(..., "--features-path"),
    labels_path: str = typer.Option(..., "--labels-path"),
    artifact_dir: str = typer.Option(..., "--artifact-dir"),
    terminal_command_out: str | None = typer.Option(None, "--terminal-command-out"),
) -> None:
    write_text(terminal_command_out, terminal_command(sys.argv))

    manifest = DailyIndexForecastDatasetManifestSummary.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
    metrics = json.loads(Path(metrics_path).read_text(encoding="utf-8"))

    session_factory = get_session_factory()
    repo = SqlAlchemyDailyIndexForecastRepository(session_factory)
    repo.update_feature_run_status(
        feature_run_id,
        status="succeeded",
        summary_metrics=metrics,
        manifest_path=manifest_path,
        features_parquet_path=features_path,
        labels_parquet_path=labels_path,
    )
    repo.update_group_status(
        group_id,
        status="succeeded",
        summary_metrics={
            "holdout": metrics.get("holdout"),
            "aggregate": metrics.get("aggregate"),
            "walk_forward": metrics.get("walk_forward"),
            "selected_alpha": metrics.get("selected_alpha"),
            "feature_columns": metrics.get("feature_columns"),
        },
    )
    repo.upsert_target(
        group_id=group_id,
        target_key="daily_index_forecast",
        task_type="regression",
        status="succeeded",
        model_artifact_path=model_path,
        metrics=metrics,
        dataset_manifest_path=manifest_path,
        feature_columns=metrics.get("feature_columns") if isinstance(metrics.get("feature_columns"), list) else None,
    )


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)

