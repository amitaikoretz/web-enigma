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
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split

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
class MaeMetrics:
    generated_at: str
    group_id: str
    n_rows: int
    mae: float
    rmse: float
    underpred_rate_q90: float | None
    underpred_rate_q95: float | None


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

    train_cfg = json.loads(train_config_json or "{}")
    random_seed = int(train_cfg.get("random_seed", 7))
    test_size = float(train_cfg.get("mae_test_size", 0.2))
    alpha = float(train_cfg.get("ridge_alpha", 1.0))

    df = pd.read_parquet(dataset_path)
    feature_cols = json.loads(feature_cols_json)
    if not isinstance(feature_cols, list) or not all(isinstance(x, str) for x in feature_cols):
        raise ValueError("--feature-cols-json must be a JSON array of strings")

    if "y_mae" in df.columns:
        y_col = "y_mae"
    elif "label_mae" in df.columns:
        y_col = "label_mae"
    else:
        raise ValueError("MAE label column not found (expected y_mae or label_mae)")

    X = df[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    y = df[y_col].astype(float).values

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_seed)

    model = Ridge(alpha=alpha, random_state=random_seed)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    mae = float(mean_absolute_error(y_test, pred))
    rmse = float(math.sqrt(mean_squared_error(y_test, pred)))

    underpred_q90 = None
    underpred_q95 = None
    for q, name in [(0.90, "q90"), (0.95, "q95")]:
        thr = float(np.quantile(y_test, q))
        tail = y_test >= thr
        if tail.any():
            rate = float(np.mean(pred[tail] < y_test[tail]))
            if name == "q90":
                underpred_q90 = rate
            else:
                underpred_q95 = rate

    out_dir = Path(artifact_dir) / "targets" / "mae"
    out_dir.mkdir(parents=True, exist_ok=True)
    model_path = out_dir / "model.json"
    metrics_path = out_dir / "metrics.json"

    serialized = {
        "type": "ridge",
        "feature_cols": feature_cols,
        "coef": model.coef_.tolist(),
        "intercept": float(model.intercept_),
        "alpha": alpha,
    }
    model_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    metrics = MaeMetrics(
        generated_at=_utc_now(),
        group_id=group_id,
        n_rows=int(len(df)),
        mae=mae,
        rmse=rmse,
        underpred_rate_q90=underpred_q90,
        underpred_rate_q95=underpred_q95,
    )
    metrics_path.write_text(json.dumps(asdict(metrics), indent=2), encoding="utf-8")

    _write_text(model_path_out, str(model_path))
    _write_text(metrics_path_out, str(metrics_path))


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)

