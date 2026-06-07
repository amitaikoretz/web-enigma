from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from app.backtests.argo_progress import (
    ARGO_PROGRESS_TOTAL,
    ThrottledProgressWriter,
    resolve_progress_file,
)
from app.daily_index_forecast.features import (
    DEFAULT_DATASET_VERSION,
    DEFAULT_FEATURE_VERSION,
    DEFAULT_LABEL_VERSION,
    DEFAULT_MODEL_VERSION,
    FEATURE_COLUMNS,
    config_hash,
    build_feature_and_label_records,
)
from app.daily_index_forecast.metrics import aggregate_nested_metrics, evaluate_predictions
from app.daily_index_forecast.models import (
    DailyIndexCostConfig,
    DailyIndexFeatureConfig,
    DailyIndexForecastCreateRequest,
    DailyIndexForecastDatasetManifestSummary,
    DailyIndexTrainConfig,
    DailyIndexUniverseConfig,
    DailyIndexWalkForwardConfig,
)
from app.daily_index_forecast.records import (
    DailyIndexFeatureRecord,
    DailyIndexLabelRecord,
    DailyIndexModelArtifact,
    DailyIndexMetrics as DailyIndexMetricsRecord,
    DailyIndexFoldMetric,
    records_to_frame,
)
from app.daily_index_forecast.walk_forward import make_walk_forward_folds
from app.config.models import DataCacheConfig


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (datetime, pd.Timestamp)):
        return value.isoformat()
    return str(value)


def _to_timestamp_series(frame: pd.DataFrame, column: str) -> pd.Series:
    ts = pd.to_datetime(frame[column], errors="coerce", utc=True)
    if ts.isna().any():
        bad = int(ts.isna().sum())
        raise ValueError(f"Column '{column}' contains {bad} invalid timestamps")
    return ts


def build_dataset_frames(
    universe: DailyIndexUniverseConfig,
    feature_config: DailyIndexFeatureConfig,
    costs: DailyIndexCostConfig,
    data_cache: DataCacheConfig,
    *,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, DailyIndexForecastDatasetManifestSummary, list[str]]:
    feature_records, label_records, manifest_counts = build_feature_and_label_records(
        universe,
        feature_config,
        costs,
        data_cache,
        force_refresh=force_refresh,
    )

    feature_df = records_to_frame(feature_records)
    label_df = records_to_frame(label_records)
    if feature_df.empty or label_df.empty:
        raise ValueError("No feature/label rows could be generated from the provided universe")

    joined = pd.merge(
        feature_df,
        label_df,
        on=["symbol", "session_date", "decision_time", "decision_timestamp"],
        how="inner",
        suffixes=("", "_label"),
    )
    if joined.empty:
        raise ValueError("No joined feature/label rows could be constructed")

    joined["session_date"] = pd.to_datetime(joined["session_date"], errors="coerce").dt.date
    joined["decision_timestamp"] = pd.to_datetime(joined["decision_timestamp"], utc=True, errors="coerce")
    joined = joined[~joined["decision_timestamp"].isna()].sort_values(
        ["decision_timestamp", "symbol", "decision_time"],
        kind="mergesort",
    )
    joined = joined.reset_index(drop=True)

    manifest = DailyIndexForecastDatasetManifestSummary(
        generated_at=_utc_now(),
        dataset_version=DEFAULT_DATASET_VERSION,
        feature_version=DEFAULT_FEATURE_VERSION,
        label_version=DEFAULT_LABEL_VERSION,
        model_version=DEFAULT_MODEL_VERSION,
        config_hash=config_hash(
            {
                "universe": universe.model_dump(mode="json"),
                "feature_config": feature_config.model_dump(mode="json"),
                "costs": costs.model_dump(mode="json"),
            }
        ),
        symbol_count=len(feature_df["symbol"].unique()),
        benchmark_symbol=universe.benchmark.symbol if universe.benchmark is not None else None,
        start_date=universe.start_date,
        end_date=universe.end_date,
        decision_times=list(universe.decision_times),
        total_source_rows=int(manifest_counts["total_source_rows"]),
        feature_rows=int(len(feature_df)),
        label_rows=int(len(label_df)),
        joined_rows=int(len(joined)),
        dropped_feature_rows=int(manifest_counts["dropped_feature_rows"]),
        dropped_label_rows=int(manifest_counts["dropped_label_rows"]),
        output_path="",
        features_path="",
        labels_path="",
        feature_columns=[col for col in FEATURE_COLUMNS if col in joined.columns],
    )
    return feature_df, label_df, joined, manifest, [col for col in FEATURE_COLUMNS if col in joined.columns]


def _fit_ridge(x_train: pd.DataFrame, y_train: np.ndarray, alpha: float) -> tuple[StandardScaler, Ridge, float]:
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_train)
    model = Ridge(alpha=alpha)
    model.fit(x_scaled, y_train)
    residuals = y_train - model.predict(x_scaled)
    residual_std = float(np.std(residuals, ddof=1)) if len(residuals) > 1 else float(np.std(residuals))
    return scaler, model, residual_std


def _predict(scaler: StandardScaler, model: Ridge, x: pd.DataFrame) -> np.ndarray:
    return np.asarray(model.predict(scaler.transform(x)), dtype=float)


def _subset(frame: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    subset = frame.loc[mask].copy()
    if subset.empty:
        return subset
    subset["decision_timestamp"] = pd.to_datetime(subset["decision_timestamp"], utc=True, errors="coerce")
    subset["session_date"] = pd.to_datetime(subset["session_date"], errors="coerce").dt.date
    return subset


def _metrics_for_split(
    *,
    split_name: str,
    y_true_bps: np.ndarray,
    predicted_bps: np.ndarray,
    threshold_bps: float,
    residual_std: float,
) -> dict[str, Any]:
    metrics = evaluate_predictions(
        y_true_bps=y_true_bps,
        predicted_bps=predicted_bps,
        threshold_bps=threshold_bps,
        residual_std=residual_std,
    )
    return {
        "split": split_name,
        **metrics,
    }


def train_daily_index_model(
    dataset: pd.DataFrame,
    *,
    group_id: str,
    feature_run_id: str,
    train_config: DailyIndexTrainConfig,
    walk_forward: DailyIndexWalkForwardConfig,
    costs: DailyIndexCostConfig,
    feature_columns: list[str],
    model_version: str = DEFAULT_MODEL_VERSION,
    feature_version: str = DEFAULT_FEATURE_VERSION,
    label_version: str = DEFAULT_LABEL_VERSION,
    dataset_version: str = DEFAULT_DATASET_VERSION,
) -> tuple[DailyIndexModelArtifact, DailyIndexMetrics, list[DailyIndexFoldMetric]]:
    if dataset.empty:
        raise ValueError("Dataset is empty")

    working = dataset.copy()
    working["session_date"] = pd.to_datetime(working["session_date"], errors="coerce").dt.date
    working["decision_timestamp"] = pd.to_datetime(working["decision_timestamp"], utc=True, errors="coerce")
    working = working[~working["decision_timestamp"].isna()].sort_values(["decision_timestamp", "symbol"], kind="mergesort")
    working = working.reset_index(drop=True)

    if not feature_columns:
        feature_columns = [col for col in FEATURE_COLUMNS if col in working.columns]
    if not feature_columns:
        raise ValueError("No feature columns were found in the dataset")

    feature_columns = [col for col in feature_columns if col in working.columns]
    progress_path = resolve_progress_file()
    progress_writer = ThrottledProgressWriter(progress_path) if progress_path is not None else None
    if progress_writer is not None:
        progress_writer.write_immediate(0)
    x_all = working[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    y_all = working["return_to_close_bps"].astype(float).to_numpy()
    threshold_bps = costs.roundtrip_bps

    folds, split = make_walk_forward_folds(
        working,
        train_days=walk_forward.train_days,
        validation_days=walk_forward.validation_days,
        test_days=walk_forward.test_days,
        step_days=walk_forward.step_days,
        embargo_days=walk_forward.embargo_days,
        min_train_rows=walk_forward.min_train_rows,
        min_validation_rows=walk_forward.min_validation_rows,
        min_test_rows=walk_forward.min_test_rows,
        min_holdout_rows=walk_forward.min_holdout_rows,
        holdout_days=walk_forward.holdout_days,
    )

    best_alpha = None
    best_score = None
    best_fold_metrics: list[dict[str, Any]] = []
    best_validation_summary: dict[str, Any] | None = None
    best_model: tuple[StandardScaler, Ridge, float] | None = None
    best_fold_id: int | None = None
    total_folds = max(1, len(folds) * max(1, len(train_config.alpha_grid)))
    completed_folds = 0

    for alpha in train_config.alpha_grid:
        per_fold_metrics: list[dict[str, Any]] = []
        validation_mae_scores: list[float] = []
        final_model: tuple[StandardScaler, Ridge, float] | None = None
        final_fold_id: int | None = None

        for fold in folds:
            train_start = pd.Timestamp(fold.train_start).tz_convert("UTC")
            train_end = pd.Timestamp(fold.train_end).tz_convert("UTC")
            validation_start = pd.Timestamp(fold.validation_start).tz_convert("UTC")
            validation_end = pd.Timestamp(fold.validation_end).tz_convert("UTC")
            test_start = pd.Timestamp(fold.test_start).tz_convert("UTC")
            test_end = pd.Timestamp(fold.test_end).tz_convert("UTC")

            train_mask = (working["decision_timestamp"] >= train_start) & (working["decision_timestamp"] < train_end)
            validation_mask = (working["decision_timestamp"] >= validation_start) & (
                working["decision_timestamp"] < validation_end
            )
            test_mask = (working["decision_timestamp"] >= test_start) & (working["decision_timestamp"] < test_end)

            x_train = x_all.loc[train_mask]
            y_train = y_all[train_mask.to_numpy()]
            x_validation = x_all.loc[validation_mask]
            y_validation = y_all[validation_mask.to_numpy()]
            x_test = x_all.loc[test_mask]
            y_test = y_all[test_mask.to_numpy()]

            if x_train.empty or x_validation.empty or x_test.empty:
                continue

            scaler, model, residual_std = _fit_ridge(x_train, y_train, alpha)
            train_pred = _predict(scaler, model, x_train)
            validation_pred = _predict(scaler, model, x_validation)
            test_pred = _predict(scaler, model, x_test)

            train_metrics = _metrics_for_split(
                split_name="train",
                y_true_bps=y_train,
                predicted_bps=train_pred,
                threshold_bps=threshold_bps,
                residual_std=residual_std,
            )
            validation_metrics = _metrics_for_split(
                split_name="validation",
                y_true_bps=y_validation,
                predicted_bps=validation_pred,
                threshold_bps=threshold_bps,
                residual_std=residual_std,
            )
            test_metrics = _metrics_for_split(
                split_name="test",
                y_true_bps=y_test,
                predicted_bps=test_pred,
                threshold_bps=threshold_bps,
                residual_std=residual_std,
            )
            per_fold_metrics.append(
                {
                    "fold_id": fold.fold_id,
                    "train_start": fold.train_start.isoformat(),
                    "train_end": fold.train_end.isoformat(),
                    "validation_start": fold.validation_start.isoformat(),
                    "validation_end": fold.validation_end.isoformat(),
                    "test_start": fold.test_start.isoformat(),
                    "test_end": fold.test_end.isoformat(),
                    "n_train": fold.n_train,
                    "n_validation": fold.n_validation,
                    "n_test": fold.n_test,
                    "train": train_metrics,
                    "validation": validation_metrics,
                    "test": test_metrics,
                }
            )
            validation_mae = validation_metrics["regression"]["mae"]
            if validation_mae is not None:
                validation_mae_scores.append(float(validation_mae))
            final_model = (scaler, model, residual_std)
            final_fold_id = fold.fold_id
            completed_folds += 1
            if progress_writer is not None:
                progress_writer.write_immediate(
                    round(min(1.0, completed_folds / total_folds) * ARGO_PROGRESS_TOTAL)
                )

        if not validation_mae_scores or final_model is None:
            continue

        score = float(np.mean(validation_mae_scores))
        if best_score is None or score < best_score:
            best_alpha = float(alpha)
            best_score = score
            best_fold_metrics = per_fold_metrics
            best_model = final_model
            best_validation_summary = aggregate_nested_metrics([m["validation"] for m in per_fold_metrics])
            best_fold_id = final_fold_id

    if best_model is None or best_alpha is None:
        raise ValueError("No trainable walk-forward folds were produced")

    scaler, model, residual_std = best_model
    holdout_start = split.holdout_start
    holdout_mask = working["decision_timestamp"] >= holdout_start
    holdout_frame = _subset(working, holdout_mask)
    if holdout_frame.empty:
        raise ValueError("Holdout split is empty")

    pre_holdout_mask = ~holdout_mask
    x_pre_holdout = x_all.loc[pre_holdout_mask]
    y_pre_holdout = y_all[pre_holdout_mask.to_numpy()]
    if x_pre_holdout.empty:
        raise ValueError("No pre-holdout rows available for final fitting")

    final_scaler, final_model, final_residual_std = _fit_ridge(x_pre_holdout, y_pre_holdout, best_alpha)
    holdout_pred = _predict(final_scaler, final_model, x_all.loc[holdout_mask])
    holdout_metrics = _metrics_for_split(
        split_name="holdout",
        y_true_bps=y_all[holdout_mask.to_numpy()],
        predicted_bps=holdout_pred,
        threshold_bps=threshold_bps,
        residual_std=final_residual_std,
    )

    aggregate_validation = aggregate_nested_metrics([fold["validation"] for fold in best_fold_metrics])
    aggregate_test = aggregate_nested_metrics([fold["test"] for fold in best_fold_metrics])

    artifact = DailyIndexModelArtifact(
        model_version=model_version,
        feature_version=feature_version,
        label_version=label_version,
        dataset_version=dataset_version,
        feature_run_id=feature_run_id,
        selected_fold_id=best_fold_id,
        selected_alpha=best_alpha,
        selected_features=feature_columns,
        scaler_mean=final_scaler.mean_.astype(float).tolist(),
        scaler_scale=final_scaler.scale_.astype(float).tolist(),
        coefficients=final_model.coef_.astype(float).tolist(),
        intercept=float(final_model.intercept_),
        residual_std=float(final_residual_std),
        costs=costs.model_dump(mode="json"),
        walk_forward={
            "train_days": walk_forward.train_days,
            "validation_days": walk_forward.validation_days,
            "test_days": walk_forward.test_days,
            "step_days": walk_forward.step_days,
            "embargo_days": walk_forward.embargo_days,
            "holdout_days": walk_forward.holdout_days,
            "n_folds": len(folds),
            "holdout_start": holdout_start.isoformat(),
        },
        holdout_metrics=holdout_metrics,
        aggregate_metrics={"validation": aggregate_validation, "test": aggregate_test},
    )

    fold_metrics = [
        DailyIndexFoldMetric.model_validate(fold)
        for fold in best_fold_metrics
    ]
    metrics = DailyIndexMetricsRecord(
        generated_at=_utc_now(),
        group_id=group_id,
        feature_run_id=feature_run_id,
        n_rows=int(len(working)),
        selected_alpha=best_alpha,
        selected_fold_id=best_fold_id,
        feature_columns=feature_columns,
        walk_forward=artifact.walk_forward,
        holdout=holdout_metrics,
        aggregate={"validation": aggregate_validation, "test": aggregate_test},
        fold_metrics=fold_metrics,
    )

    if progress_writer is not None:
        progress_writer.write_immediate(ARGO_PROGRESS_TOTAL)

    return artifact, metrics, fold_metrics


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=_json_default), encoding="utf-8")


def save_dataset_artifacts(
    *,
    output_dir: Path,
    feature_df: pd.DataFrame,
    label_df: pd.DataFrame,
    joined_df: pd.DataFrame,
    manifest: DailyIndexForecastDatasetManifestSummary,
) -> tuple[Path, Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    features_path = output_dir / "features.parquet"
    labels_path = output_dir / "labels.parquet"
    dataset_path = output_dir / "dataset.parquet"
    manifest_path = output_dir / "manifest.json"

    feature_df.to_parquet(features_path, index=False)
    label_df.to_parquet(labels_path, index=False)
    joined_df.to_parquet(dataset_path, index=False)
    manifest.output_path = str(dataset_path)  # type: ignore[misc]
    manifest.features_path = str(features_path)  # type: ignore[misc]
    manifest.labels_path = str(labels_path)  # type: ignore[misc]
    write_json(manifest_path, manifest.model_dump(mode="json"))
    return dataset_path, features_path, labels_path, manifest_path
