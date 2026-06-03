from __future__ import annotations

import json
import shlex
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.db.session import get_session_factory
from app.db.models import BacktestJob

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
    _write_text(terminal_command_out, _terminal_command(sys.argv))
    # Pre-create output parameter files so Argo can always collect them, even on failure.
    _write_text(dataset_path_out, "")
    _write_text(manifest_path_out, "")
    _write_text(feature_cols_out, "")

    backtest_ids = json.loads(backtest_ids_json)
    if not isinstance(backtest_ids, list) or not all(isinstance(x, str) and x for x in backtest_ids):
        raise ValueError("--backtest-ids-json must be a JSON array of strings")

    # dataset_config_json reserved for future shaping (filters, dedupe policy, etc.)
    _ = json.loads(dataset_config_json or "{}")

    out_dir = Path(artifact_dir) / "dataset"
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = out_dir / "dataset.parquet"
    manifest_path = out_dir / "manifest.json"

    session_factory = get_session_factory()

    label_frames: list[pd.DataFrame] = []
    feature_frames: list[pd.DataFrame] = []
    for backtest_id in backtest_ids:
        with session_factory() as session:
            row = session.get(BacktestJob, backtest_id)
            if row is None:
                raise ValueError(f"Backtest '{backtest_id}' not found in DB")
            if not row.labels_parquet_path or not row.features_parquet_path:
                raise ValueError(f"Backtest '{backtest_id}' missing labels/features parquet paths")
            labels_path = Path(row.labels_parquet_path)
            feats_path = Path(row.features_parquet_path)
        if not labels_path.exists():
            raise FileNotFoundError(f"labels parquet not found: {labels_path}")
        if not feats_path.exists():
            raise FileNotFoundError(f"features parquet not found: {feats_path}")

        labels = pd.read_parquet(labels_path)
        feats = pd.read_parquet(feats_path)
        labels["backtest_id"] = backtest_id
        feats["backtest_id"] = backtest_id
        label_frames.append(labels)
        feature_frames.append(feats)

    labels_all = pd.concat(label_frames, ignore_index=True) if label_frames else pd.DataFrame()
    feats_all = pd.concat(feature_frames, ignore_index=True) if feature_frames else pd.DataFrame()

    key = "candidate_id"
    if key not in labels_all.columns or key not in feats_all.columns:
        raise ValueError("Expected 'candidate_id' in both labels and features parquet")

    joined = labels_all.merge(feats_all, on=[key, "backtest_id"], how="inner", suffixes=("_label", ""))
    if joined.empty:
        raise ValueError("Joined dataset is empty; check candidate_id alignment between labels/features")

    # Feature columns = non-label columns, excluding obvious identifiers.
    exclude_prefixes = ("label_",)
    exclude_exact = {key, "backtest_id"}
    feature_cols: list[str] = []
    for col in joined.columns:
        if col in exclude_exact:
            continue
        if any(col.startswith(p) for p in exclude_prefixes):
            continue
        if col.endswith("_label"):
            continue
        feature_cols.append(col)

    joined.to_parquet(dataset_path, index=False)
    manifest = DatasetManifest(
        generated_at=_utc_now(),
        group_id=group_id,
        backtest_ids=backtest_ids,
        input_rows=int(len(labels_all) + len(feats_all)),
        joined_rows=int(len(joined)),
        labels_rows=int(len(labels_all)),
        features_rows=int(len(feats_all)),
        dataset_path=str(dataset_path),
        feature_columns=feature_cols,
    )
    manifest_path.write_text(json.dumps(asdict(manifest), indent=2), encoding="utf-8")

    _write_text(dataset_path_out, str(dataset_path))
    _write_text(manifest_path_out, str(manifest_path))
    _write_text(feature_cols_out, json.dumps(feature_cols))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
