from __future__ import annotations

from collections.abc import Mapping
from math import sqrt
from statistics import NormalDist
from typing import Any

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
)


def probability_from_regression(predicted_bps: np.ndarray, threshold_bps: float, residual_std: float) -> np.ndarray:
    if residual_std <= 0:
        return (predicted_bps >= threshold_bps).astype(float)
    nd = NormalDist()
    values = [(threshold_bps - float(value)) / residual_std for value in predicted_bps]
    return np.asarray([1.0 - nd.cdf(value) for value in values], dtype=float)


def quantile_interval(predicted_bps: np.ndarray, residual_std: float, lower_q: float, upper_q: float) -> tuple[np.ndarray, np.ndarray]:
    nd = NormalDist()
    lower_z = nd.inv_cdf(lower_q)
    upper_z = nd.inv_cdf(upper_q)
    lower = predicted_bps + lower_z * residual_std
    upper = predicted_bps + upper_z * residual_std
    return lower, upper


def interval_metrics(y_true: np.ndarray, predicted: np.ndarray, residual_std: float) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for lower_q, upper_q, name in [(0.25, 0.75, "50"), (0.10, 0.90, "80"), (0.05, 0.95, "90"), (0.025, 0.975, "95")]:
        lower, upper = quantile_interval(predicted, residual_std, lower_q, upper_q)
        covered = (y_true >= lower) & (y_true <= upper)
        out[f"coverage_{name}"] = float(np.mean(covered)) if len(y_true) else None
        out[f"width_{name}"] = float(np.mean(upper - lower)) if len(y_true) else None
    return out


def calibration_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, float | None]:
    if len(y_true) == 0:
        return {"brier": None, "logloss": None, "ece": None, "positive_rate": None, "predicted_positive_rate": None}

    result = {
        "brier": float(brier_score_loss(y_true, probabilities)),
        "logloss": float(log_loss(y_true, probabilities, labels=[0, 1])),
        "positive_rate": float(np.mean(y_true)),
        "predicted_positive_rate": float(np.mean(probabilities)),
    }
    bins = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    total = len(y_true)
    for idx in range(len(bins) - 1):
        if idx == len(bins) - 2:
            mask = (probabilities >= bins[idx]) & (probabilities <= bins[idx + 1])
        else:
            mask = (probabilities >= bins[idx]) & (probabilities < bins[idx + 1])
        if not mask.any():
            continue
        bin_prob = float(np.mean(probabilities[mask]))
        bin_obs = float(np.mean(y_true[mask]))
        ece += abs(bin_prob - bin_obs) * (mask.sum() / total)
    result["ece"] = float(ece)
    return result


def classification_metrics(y_true: np.ndarray, probabilities: np.ndarray, threshold: float = 0.5) -> dict[str, float | None]:
    if len(y_true) == 0:
        return {
            "accuracy": None,
            "balanced_accuracy": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "roc_auc": None,
        }
    y_pred = (probabilities >= threshold).astype(int)
    try:
        roc = float(roc_auc_score(y_true, probabilities))
    except ValueError:
        roc = None
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": roc,
    }


def regression_metrics(y_true: np.ndarray, predicted: np.ndarray) -> dict[str, float | None]:
    if len(y_true) == 0:
        return {"mae": None, "rmse": None, "mse": None, "r2": None, "mean_error": None}
    residual = y_true - predicted
    return {
        "mae": float(mean_absolute_error(y_true, predicted)),
        "rmse": float(sqrt(mean_squared_error(y_true, predicted))),
        "mse": float(mean_squared_error(y_true, predicted)),
        "r2": float(r2_score(y_true, predicted)),
        "mean_error": float(np.mean(residual)),
    }


def evaluate_predictions(
    *,
    y_true_bps: np.ndarray,
    predicted_bps: np.ndarray,
    threshold_bps: float,
    residual_std: float,
) -> dict[str, Any]:
    positive_after_cost = (y_true_bps > threshold_bps).astype(int)
    probabilities = probability_from_regression(predicted_bps, threshold_bps, residual_std)
    regression = regression_metrics(y_true_bps, predicted_bps)
    classification = classification_metrics(positive_after_cost, probabilities)
    calibration = calibration_metrics(positive_after_cost, probabilities)
    intervals = interval_metrics(y_true_bps, predicted_bps, residual_std)
    return {
        "regression": regression,
        "classification": classification,
        "calibration": calibration,
        "quantile": intervals,
        "positive_rate": float(np.mean(positive_after_cost)) if len(positive_after_cost) else None,
        "predicted_positive_rate": float(np.mean(probabilities >= 0.5)) if len(probabilities) else None,
    }


def aggregate_nested_metrics(items: list[dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {}

    def _aggregate(values: list[Any]) -> Any:
        if not values:
            return None
        if all(isinstance(value, Mapping) for value in values):
            keys = sorted({str(key) for value in values if isinstance(value, Mapping) for key in value.keys()})
            return {key: _aggregate([value.get(key) for value in values if isinstance(value, Mapping)]) for key in keys}
        numbers: list[float] = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, (int, float, np.integer, np.floating)):
                numbers.append(float(value))
        if not numbers:
            return None
        return float(np.mean(numbers))

    keys = sorted({key for item in items for key in item.keys()})
    return {key: _aggregate([item.get(key) for item in items]) for key in keys}

