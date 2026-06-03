from __future__ import annotations

import json
import math
import shlex
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class StopMetrics:
    generated_at: str
    group_id: str
    n_rows: int
    positive_rate: float
    brier_raw: float
    brier_calibrated: float
    logloss_calibrated: float
    auc_calibrated: float | None
    reliability_bins: list[dict[str, Any]]


@app.command(help="Train stop-probability model and write model + metrics (for Argo workflow).")
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

    from sklearn.calibration import calibration_curve
    from sklearn.isotonic import IsotonicRegression
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score
    from sklearn.model_selection import train_test_split

    train_cfg = json.loads(train_config_json or "{}")
    random_seed = int(train_cfg.get("random_seed", 7))
    test_size = float(train_cfg.get("calibration_test_size", 0.2))
    n_bins = int(train_cfg.get("calibration_bins", 10))

    df = pd.read_parquet(dataset_path)
    feature_cols = json.loads(feature_cols_json)
    if not isinstance(feature_cols, list) or not all(isinstance(x, str) for x in feature_cols):
        raise ValueError("--feature-cols-json must be a JSON array of strings")

    if "y_stop" in df.columns:
        y_col = "y_stop"
    elif "label_hit_stop" in df.columns:
        y_col = "label_hit_stop"
    else:
        raise ValueError("Stop label column not found (expected y_stop or label_hit_stop)")

    X = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    y = df[y_col].astype(int).values

    X_train, X_calib, y_train, y_calib = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=random_seed,
        stratify=y if len(np.unique(y)) > 1 else None,
    )

    model = LogisticRegression(max_iter=500, n_jobs=1)
    model.fit(X_train, y_train)
    p_raw = model.predict_proba(X_calib)[:, 1]

    iso = IsotonicRegression(out_of_bounds="clip")
    iso.fit(p_raw, y_calib)
    p_cal = iso.transform(p_raw)

    brier_raw = float(brier_score_loss(y_calib, p_raw))
    brier_cal = float(brier_score_loss(y_calib, p_cal))
    ll_cal = float(log_loss(y_calib, p_cal, labels=[0, 1]))
    auc = float(roc_auc_score(y_calib, p_cal)) if len(np.unique(y_calib)) > 1 else None

    prob_true, prob_pred = calibration_curve(y_calib, p_cal, n_bins=n_bins, strategy="quantile")
    reliability = [
        {"p_mean": float(p), "y_mean": float(yv)}
        for p, yv in zip(prob_pred.tolist(), prob_true.tolist(), strict=False)
    ]

    out_dir = Path(artifact_dir) / "targets" / "stop_prob"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "model.json"
    metrics_path = out_dir / "metrics.json"

    # Serialize minimal model for v1: coefficients + intercept + iso calibration breakpoints.
    serialized = {
        "type": "logreg+isotonic",
        "feature_cols": feature_cols,
        "coef": model.coef_.tolist(),
        "intercept": model.intercept_.tolist(),
        "iso_x_thresholds": iso.X_thresholds_.tolist(),  # type: ignore[attr-defined]
        "iso_y_thresholds": iso.y_thresholds_.tolist(),  # type: ignore[attr-defined]
    }
    model_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    metrics = StopMetrics(
        generated_at=_utc_now(),
        group_id=group_id,
        n_rows=int(len(df)),
        positive_rate=float(np.mean(y)),
        brier_raw=brier_raw,
        brier_calibrated=brier_cal,
        logloss_calibrated=ll_cal,
        auc_calibrated=auc,
        reliability_bins=reliability,
    )
    metrics_path.write_text(json.dumps(asdict(metrics), indent=2), encoding="utf-8")

    _write_text(model_path_out, str(model_path))
    _write_text(metrics_path_out, str(metrics_path))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
