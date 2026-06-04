from __future__ import annotations

import json
import math
import shlex
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import mean
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.risk.dataset.feature_columns import select_risk_feature_columns
from app.risk.walk_forward import make_walk_forward_folds, resolve_walk_forward_config

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


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)


@dataclass(frozen=True)
class MaeMetrics:
    generated_at: str
    group_id: str
    n_rows: int
    walk_forward: dict[str, Any]
    fold_metrics: list[dict[str, Any]]
    aggregate: dict[str, dict[str, float | None]]


def _metric_mean(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return float(mean(valid))


@app.command(help="Train MAE regression model and write model + metrics (for Argo workflow).")
def main(
    group_id: str = typer.Option(..., "--group-id"),
    dataset_path: str = typer.Option(..., "--dataset-path"),
    manifest_path: str = typer.Option(..., "--manifest-path"),
    feature_cols_json: str = typer.Option(..., "--feature-cols-json"),
    train_config_json: str = typer.Option("{}", "--train-config-json"),
    artifact_dir: str = typer.Option(..., "--artifact-dir"),
    model_path_out: str = typer.Option(..., "--model-path-out"),
    metrics_path_out: str = typer.Option(..., "--metrics-path-out"),
    terminal_command_out: str | None = typer.Option(
        None,
        "--terminal-command-out",
        help="Write the invoked command line to this path (for Argo output parameters)",
    ),
) -> None:
    _write_text(terminal_command_out, _terminal_command(sys.argv))
    # Pre-create output parameter files so Argo can always collect them, even on failure.
    _write_text(model_path_out, "")
    _write_text(metrics_path_out, "")

    from sklearn.metrics import mean_absolute_error, mean_squared_error
    from sklearn.linear_model import Ridge

    train_cfg = json.loads(train_config_json or "{}")
    alpha = float(train_cfg.get("ridge_alpha", 1.0))
    random_seed = int(train_cfg.get("random_seed", 7))

    df = pd.read_parquet(dataset_path)
    feature_cols = json.loads(feature_cols_json)
    if not isinstance(feature_cols, list) or not all(isinstance(x, str) for x in feature_cols):
        raise ValueError("--feature-cols-json must be a JSON array of strings")

    mae_label_candidates = ("mae_abs_pct", "y_mae", "label_mae")
    y_col = next((col for col in mae_label_candidates if col in df.columns), None)
    if y_col is None:
        raise ValueError("MAE label column not found (expected mae_abs_pct, y_mae, or label_mae)")

    feature_cols, skipped_feature_cols = select_risk_feature_columns(df, feature_cols)
    if skipped_feature_cols:
        typer.echo("Skipping non-feature columns from MAE training: " + ", ".join(skipped_feature_cols), err=True)
    if not feature_cols:
        raise ValueError("No valid numeric MAE features remained after filtering")

    walk_forward = resolve_walk_forward_config(df, train_cfg)
    folds = make_walk_forward_folds(df, walk_forward)
    if not folds:
        raise ValueError(
            "No walk-forward folds could be created from the dataset; adjust the walk-forward window sizes "
            "or provide more historical data"
        )

    timestamp_col = walk_forward.timestamp_column
    ts = pd.to_datetime(df[timestamp_col], utc=True, errors="coerce")
    ordered_df = df.assign(__wf_timestamp=ts).sort_values(["__wf_timestamp"], kind="mergesort")
    X_all = ordered_df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    y_all = ordered_df[y_col].astype(float).values
    ts_all = ordered_df["__wf_timestamp"]

    fold_metrics: list[dict[str, Any]] = []
    last_model: Ridge | None = None
    last_fold_id: int | None = None

    for fold in folds:
        train_mask = (ts_all >= fold.train_start) & (ts_all < fold.train_end)
        validation_mask = (ts_all >= fold.validation_start) & (ts_all < fold.validation_end)
        test_mask = (ts_all >= fold.test_start) & (ts_all < fold.test_end)

        x_train = X_all.loc[train_mask]
        y_train = y_all[train_mask.to_numpy()]
        x_validation = X_all.loc[validation_mask]
        y_validation = y_all[validation_mask.to_numpy()]
        x_test = X_all.loc[test_mask]
        y_test = y_all[test_mask.to_numpy()]

        model = Ridge(alpha=alpha, random_state=random_seed)
        model.fit(x_train, y_train)
        pred_validation = model.predict(x_validation)
        pred_test = model.predict(x_test)

        validation_metrics = {
            "mae": float(mean_absolute_error(y_validation, pred_validation)),
            "rmse": float(math.sqrt(mean_squared_error(y_validation, pred_validation))),
            "underpred_rate_q90": None,
            "underpred_rate_q95": None,
        }
        test_metrics = {
            "mae": float(mean_absolute_error(y_test, pred_test)),
            "rmse": float(math.sqrt(mean_squared_error(y_test, pred_test))),
            "underpred_rate_q90": None,
            "underpred_rate_q95": None,
        }
        for q, name in [(0.90, "q90"), (0.95, "q95")]:
            thr_validation = float(np.quantile(y_validation, q))
            validation_tail = y_validation >= thr_validation
            if validation_tail.any():
                validation_metrics[f"underpred_rate_{name}"] = float(
                    np.mean(pred_validation[validation_tail] < y_validation[validation_tail])
                )

            thr_test = float(np.quantile(y_test, q))
            test_tail = y_test >= thr_test
            if test_tail.any():
                test_metrics[f"underpred_rate_{name}"] = float(np.mean(pred_test[test_tail] < y_test[test_tail]))

        fold_metrics.append(
            {
                "fold_id": fold.fold_id,
                "train_start": str(fold.train_start),
                "train_end": str(fold.train_end),
                "validation_start": str(fold.validation_start),
                "validation_end": str(fold.validation_end),
                "test_start": str(fold.test_start),
                "test_end": str(fold.test_end),
                "n_train": fold.n_train,
                "n_validation": fold.n_validation,
                "n_test": fold.n_test,
                "validation": validation_metrics,
                "test": test_metrics,
            }
        )
        last_model = model
        last_fold_id = fold.fold_id

    assert last_model is not None
    assert last_fold_id is not None

    aggregate = {
        "validation": {
            "mae_mean": _metric_mean([fold["validation"]["mae"] for fold in fold_metrics]),
            "rmse_mean": _metric_mean([fold["validation"]["rmse"] for fold in fold_metrics]),
            "underpred_rate_q90_mean": _metric_mean(
                [fold["validation"]["underpred_rate_q90"] for fold in fold_metrics]
            ),
            "underpred_rate_q95_mean": _metric_mean(
                [fold["validation"]["underpred_rate_q95"] for fold in fold_metrics]
            ),
        },
        "test": {
            "mae_mean": _metric_mean([fold["test"]["mae"] for fold in fold_metrics]),
            "rmse_mean": _metric_mean([fold["test"]["rmse"] for fold in fold_metrics]),
            "underpred_rate_q90_mean": _metric_mean([fold["test"]["underpred_rate_q90"] for fold in fold_metrics]),
            "underpred_rate_q95_mean": _metric_mean([fold["test"]["underpred_rate_q95"] for fold in fold_metrics]),
        },
    }

    out_dir = Path(artifact_dir) / "targets" / "mae"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "model.json"
    metrics_path = out_dir / "metrics.json"

    serialized = {
        "type": "ridge",
        "selected_fold_id": last_fold_id,
        "walk_forward": {
            "timestamp_column": timestamp_col,
            "train_days": walk_forward.train_days,
            "test_days": walk_forward.test_days,
            "step_days": walk_forward.step_days,
            "calibration_fraction": walk_forward.calibration_fraction,
            "embargo_bars": walk_forward.embargo_bars,
            "n_folds": len(folds),
        },
        "feature_cols": feature_cols,
        "coef": last_model.coef_.tolist(),
        "intercept": float(last_model.intercept_),
        "alpha": alpha,
    }
    model_path.write_text(json.dumps(serialized, indent=2, default=_json_default), encoding="utf-8")

    metrics = MaeMetrics(
        generated_at=_utc_now(),
        group_id=group_id,
        n_rows=int(len(df)),
        walk_forward={
            "timestamp_column": timestamp_col,
            "train_days": walk_forward.train_days,
            "test_days": walk_forward.test_days,
            "step_days": walk_forward.step_days,
            "calibration_fraction": walk_forward.calibration_fraction,
            "embargo_bars": walk_forward.embargo_bars,
            "n_folds": len(folds),
            "selected_fold_id": last_fold_id,
        },
        fold_metrics=fold_metrics,
        aggregate=aggregate,
    )
    metrics_path.write_text(json.dumps(asdict(metrics), indent=2, default=_json_default), encoding="utf-8")

    _write_text(model_path_out, str(model_path))
    _write_text(metrics_path_out, str(metrics_path))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
