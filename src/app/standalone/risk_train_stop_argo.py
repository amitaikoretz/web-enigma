from __future__ import annotations

import json
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
class StopMetrics:
    generated_at: str
    group_id: str
    n_rows: int
    positive_rate: float
    walk_forward: dict[str, Any]
    fold_metrics: list[dict[str, Any]]
    aggregate: dict[str, dict[str, float | None]]


def _positive_probability(model: Any, x: pd.DataFrame | np.ndarray) -> np.ndarray:
    probabilities = model.predict_proba(x)
    classes = list(getattr(model, "classes_", []))
    if len(classes) == 1:
        return np.full(len(x), 1.0 if classes[0] == 1 else 0.0, dtype=float)
    if 1 in classes:
        idx = classes.index(1)
    else:
        idx = len(classes) - 1
    return np.asarray(probabilities[:, idx], dtype=float)


def _metric_mean(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return float(mean(valid))


def _calibration_bins(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> list[dict[str, Any]]:
    try:
        from sklearn.calibration import calibration_curve

        prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="quantile")
        return [
            {"p_mean": float(p), "y_mean": float(yv)}
            for p, yv in zip(prob_pred.tolist(), prob_true.tolist(), strict=False)
        ]
    except Exception:
        return []


def _fit_stop_model(x_train: pd.DataFrame, y_train: np.ndarray) -> tuple[Any, str]:
    from sklearn.dummy import DummyClassifier
    from sklearn.linear_model import LogisticRegression

    if len(np.unique(y_train)) < 2:
        model: Any = DummyClassifier(strategy="prior")
        model.fit(x_train, y_train)
        return model, "prior"

    model = LogisticRegression(max_iter=500)
    model.fit(x_train, y_train)
    return model, "logreg"


def _fit_calibrator(p_raw: np.ndarray, y_calib: np.ndarray) -> tuple[Any | None, str]:
    from sklearn.isotonic import IsotonicRegression

    if len(np.unique(y_calib)) < 2 or len(np.unique(p_raw)) < 2:
        return None, "identity"
    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(p_raw, y_calib)
    return calibrator, "isotonic"


def _serialize_stop_model(
    *,
    model: Any,
    model_type: str,
    calibrator: Any | None,
    feature_cols: list[str],
    selected_fold_id: int,
    walk_forward: dict[str, Any],
    train_positive_rate: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": f"{model_type}+{'isotonic' if calibrator is not None else 'identity'}",
        "selected_fold_id": selected_fold_id,
        "walk_forward": walk_forward,
        "feature_cols": feature_cols,
    }
    classes = list(getattr(model, "classes_", []))
    if hasattr(model, "coef_"):
        payload["coef"] = np.asarray(model.coef_).tolist()
        payload["intercept"] = np.asarray(model.intercept_).tolist()
        payload["classes"] = classes
    else:
        payload["classes"] = classes
        payload["positive_rate"] = train_positive_rate
    if calibrator is not None:
        payload["calibration_type"] = "isotonic"
        payload["iso_x_thresholds"] = calibrator.X_thresholds_.tolist()  # type: ignore[attr-defined]
        payload["iso_y_thresholds"] = calibrator.y_thresholds_.tolist()  # type: ignore[attr-defined]
    else:
        payload["calibration_type"] = "identity"
    return payload


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

    from sklearn.metrics import brier_score_loss, log_loss, roc_auc_score

    train_cfg = json.loads(train_config_json or "{}")
    n_bins = int(train_cfg.get("calibration_bins", 10))

    df = pd.read_parquet(dataset_path)
    feature_cols = json.loads(feature_cols_json)
    if not isinstance(feature_cols, list) or not all(isinstance(x, str) for x in feature_cols):
        raise ValueError("--feature-cols-json must be a JSON array of strings")

    stop_label_candidates = ("hit_stop_before_target", "y_stop", "label_hit_stop")
    y_col = next((col for col in stop_label_candidates if col in df.columns), None)
    if y_col is None:
        raise ValueError(
            "Stop label column not found (expected hit_stop_before_target, y_stop, or label_hit_stop)"
        )

    feature_cols, skipped_feature_cols = select_risk_feature_columns(df, feature_cols)
    if skipped_feature_cols:
        typer.echo(
            "Skipping non-feature columns from stop-probability training: " + ", ".join(skipped_feature_cols),
            err=True,
        )
    if not feature_cols:
        raise ValueError("No valid numeric stop-probability features remained after filtering")

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
    y_all = ordered_df[y_col].astype(int).values
    ts_all = ordered_df["__wf_timestamp"]

    fold_metrics: list[dict[str, Any]] = []
    last_model: Any | None = None
    last_model_type: str | None = None
    last_calibrator: Any | None = None
    last_fold_id: int | None = None
    last_train_positive_rate: float | None = None

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

        model, model_type = _fit_stop_model(x_train, y_train)
        p_validation_raw = _positive_probability(model, x_validation)
        p_test_raw = _positive_probability(model, x_test)
        calibrator, calibration_type = _fit_calibrator(p_validation_raw, y_validation)
        p_validation_cal = calibrator.transform(p_validation_raw) if calibrator is not None else p_validation_raw
        p_test_cal = calibrator.transform(p_test_raw) if calibrator is not None else p_test_raw

        validation_metrics = {
            "brier_raw": float(brier_score_loss(y_validation, p_validation_raw)),
            "brier_calibrated": float(brier_score_loss(y_validation, p_validation_cal)),
            "logloss_calibrated": float(log_loss(y_validation, p_validation_cal, labels=[0, 1])),
            "auc_calibrated": float(roc_auc_score(y_validation, p_validation_cal))
            if len(np.unique(y_validation)) > 1
            else None,
            "reliability_bins": _calibration_bins(y_validation, p_validation_cal, n_bins=n_bins),
        }
        test_metrics = {
            "brier_raw": float(brier_score_loss(y_test, p_test_raw)),
            "brier_calibrated": float(brier_score_loss(y_test, p_test_cal)),
            "logloss_calibrated": float(log_loss(y_test, p_test_cal, labels=[0, 1])),
            "auc_calibrated": float(roc_auc_score(y_test, p_test_cal)) if len(np.unique(y_test)) > 1 else None,
            "reliability_bins": _calibration_bins(y_test, p_test_cal, n_bins=n_bins),
        }

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
                "model_type": model_type,
                "calibration_type": calibration_type,
                "validation": validation_metrics,
                "test": test_metrics,
            }
        )
        last_model = model
        last_model_type = model_type
        last_calibrator = calibrator
        last_fold_id = fold.fold_id
        last_train_positive_rate = float(np.mean(y_train))

    assert last_model is not None
    assert last_model_type is not None
    assert last_fold_id is not None
    assert last_train_positive_rate is not None

    aggregate = {
        "validation": {
            "brier_raw_mean": _metric_mean([fold["validation"]["brier_raw"] for fold in fold_metrics]),
            "brier_calibrated_mean": _metric_mean([fold["validation"]["brier_calibrated"] for fold in fold_metrics]),
            "logloss_calibrated_mean": _metric_mean(
                [fold["validation"]["logloss_calibrated"] for fold in fold_metrics]
            ),
            "auc_calibrated_mean": _metric_mean([fold["validation"]["auc_calibrated"] for fold in fold_metrics]),
        },
        "test": {
            "brier_raw_mean": _metric_mean([fold["test"]["brier_raw"] for fold in fold_metrics]),
            "brier_calibrated_mean": _metric_mean([fold["test"]["brier_calibrated"] for fold in fold_metrics]),
            "logloss_calibrated_mean": _metric_mean([fold["test"]["logloss_calibrated"] for fold in fold_metrics]),
            "auc_calibrated_mean": _metric_mean([fold["test"]["auc_calibrated"] for fold in fold_metrics]),
        },
    }

    out_dir = Path(artifact_dir) / "targets" / "stop_prob"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "model.json"
    metrics_path = out_dir / "metrics.json"

    serialized = _serialize_stop_model(
        model=last_model,
        model_type=last_model_type,
        calibrator=last_calibrator,
        feature_cols=feature_cols,
        selected_fold_id=last_fold_id,
        walk_forward={
            "timestamp_column": timestamp_col,
            "train_days": walk_forward.train_days,
            "test_days": walk_forward.test_days,
            "step_days": walk_forward.step_days,
            "calibration_fraction": walk_forward.calibration_fraction,
            "embargo_bars": walk_forward.embargo_bars,
            "n_folds": len(folds),
        },
        train_positive_rate=last_train_positive_rate,
    )
    model_path.write_text(json.dumps(serialized, indent=2, default=_json_default), encoding="utf-8")

    metrics = StopMetrics(
        generated_at=_utc_now(),
        group_id=group_id,
        n_rows=int(len(df)),
        positive_rate=float(np.mean(y_all)),
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
