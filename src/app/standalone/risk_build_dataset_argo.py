from __future__ import annotations

import json
import shlex
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.db.session import get_session_factory
from app.db.models import BacktestJob
from app.risk.dataset import RiskDatasetReader, build_risk_dataset
from app.risk.dataset.feature_columns import select_risk_feature_columns
from app.risk.models import RiskDatasetConfig
from app.script_logging import emit_terminal_command, emit_warning

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class DatasetManifest:
    generated_at: str
    group_id: str
    backtest_ids: list[str]
    input_rows: int
    joined_rows: int
    labels_rows: int
    features_rows: int
    dataset_path: str
    feature_columns: list[str]


@app.command(help="Build a pooled risk model dataset from one or more backtests (for Argo workflow).")
def main(
    group_id: str = typer.Option(..., "--group-id"),
    backtest_ids_json: str = typer.Option(..., "--backtest-ids-json", help="JSON list of backtest ids"),
    dataset_config_json: str = typer.Option("{}", "--dataset-config-json", help="JSON config (reserved for v2)"),
    artifact_dir: str = typer.Option(..., "--artifact-dir", help="Shared artifact directory for this group"),
    dataset_path_out: str = typer.Option(..., "--dataset-path-out", help="Write dataset parquet path to this file"),
    manifest_path_out: str = typer.Option(..., "--manifest-path-out", help="Write dataset manifest path to this file"),
    feature_cols_out: str = typer.Option(..., "--feature-cols-out", help="Write feature columns JSON to this file"),
    terminal_command_out: str | None = typer.Option(
        None,
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="risk_build_dataset_argo")
    # Pre-create output parameter files so Argo can always collect them, even on failure.
    _write_text(dataset_path_out, "")
    _write_text(manifest_path_out, "")
    _write_text(feature_cols_out, "")

    backtest_ids = json.loads(backtest_ids_json)
    if not isinstance(backtest_ids, list) or not all(isinstance(x, str) and x for x in backtest_ids):
        raise ValueError("--backtest-ids-json must be a JSON array of strings")

    dataset_config_raw = json.loads(dataset_config_json or "{}")
    if not isinstance(dataset_config_raw, dict):
        raise ValueError("--dataset-config-json must be a JSON object")
    risk_dataset_config = RiskDatasetConfig.model_validate(dataset_config_raw.get("risk_dataset", dataset_config_raw))

    out_dir = Path(artifact_dir) / "dataset"
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "dataset.parquet"

    session_factory = get_session_factory()
    report_paths: list[Path] = []
    for backtest_id in backtest_ids:
        with session_factory() as session:
            row = session.get(BacktestJob, backtest_id)
            if row is None:
                raise ValueError(f"Backtest '{backtest_id}' not found in DB")
            if not row.report_json_path:
                raise ValueError(f"Backtest '{backtest_id}' missing report JSON path")
            report_paths.append(Path(row.report_json_path))

    dataset_manifest = build_risk_dataset(report_paths, output_path=dataset_path, config=risk_dataset_config)
    manifest_path = dataset_path.with_suffix(".manifest.json")
    reader = RiskDatasetReader.from_manifest_path(manifest_path)
    joined = reader.load()

    feature_cols, skipped_feature_cols = select_risk_feature_columns(joined)
    if skipped_feature_cols:
        emit_warning(
            "risk-feature-filter",
            "Skipping non-feature columns from risk model inputs: " + ", ".join(skipped_feature_cols),
            script="risk_build_dataset_argo",
        )

    manifest = DatasetManifest(
        generated_at=_utc_now(),
        group_id=group_id,
        backtest_ids=backtest_ids,
        input_rows=int(dataset_manifest.labeled_rows + dataset_manifest.feature_rows),
        joined_rows=int(dataset_manifest.joined_rows),
        labels_rows=int(dataset_manifest.labeled_rows),
        features_rows=int(dataset_manifest.feature_rows),
        dataset_path=str(reader.output_path),
        feature_columns=feature_cols,
    )
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")

    _write_text(dataset_path_out, str(reader.output_path))
    _write_text(manifest_path_out, str(manifest_path))
    _write_text(feature_cols_out, json.dumps(feature_cols))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
