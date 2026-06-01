from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.db.session import get_session_factory
from app.backtests.persistence import SqlAlchemyBacktestJobRepository
from app.risk.persistence import SqlAlchemyRiskModelRepository

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


@app.command(help="Register trained risk model artifacts + metrics in the DB (for Argo workflow).")
def main(
    group_id: str = typer.Option(..., "--group-id"),
    manifest_path: str = typer.Option(..., "--manifest-path"),
    feature_cols_json: str = typer.Option(..., "--feature-cols-json"),
    stop_model_path: str = typer.Option(..., "--stop-model-path"),
    stop_metrics_path: str = typer.Option(..., "--stop-metrics-path"),
    mae_model_path: str = typer.Option(..., "--mae-model-path"),
    mae_metrics_path: str = typer.Option(..., "--mae-metrics-path"),
    terminal_command_out: str | None = typer.Option(
        None,
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    _write_text(terminal_command_out, _terminal_command(sys.argv))

    feature_cols = json.loads(feature_cols_json)
    if not isinstance(feature_cols, list) or not all(isinstance(x, str) for x in feature_cols):
        raise ValueError("--feature-cols-json must be a JSON array of strings")

    stop_metrics = json.loads(Path(stop_metrics_path).read_text(encoding="utf-8"))
    mae_metrics = json.loads(Path(mae_metrics_path).read_text(encoding="utf-8"))

    session_factory = get_session_factory()
    risk_repo = SqlAlchemyRiskModelRepository(session_factory)

    risk_repo.upsert_target(
        group_id=group_id,
        target_key="stop_prob",
        task_type="classification",
        status="succeeded",
        model_artifact_path=stop_model_path,
        metrics=stop_metrics,
        dataset_manifest_path=manifest_path,
        feature_columns=feature_cols,
    )
    risk_repo.upsert_target(
        group_id=group_id,
        target_key="mae",
        task_type="regression",
        status="succeeded",
        model_artifact_path=mae_model_path,
        metrics=mae_metrics,
        dataset_manifest_path=manifest_path,
        feature_columns=feature_cols,
    )

    risk_repo.update_group_status(
        group_id,
        status="succeeded",
        summary_metrics={
            "stop_prob": {
                "brier_calibrated": stop_metrics.get("brier_calibrated"),
                "auc_calibrated": stop_metrics.get("auc_calibrated"),
            },
            "mae": {
                "mae": mae_metrics.get("mae"),
                "rmse": mae_metrics.get("rmse"),
            },
        },
    )


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)

