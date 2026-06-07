from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.api.helpers.market_data import frame_to_rows
from app.api.schemas.market_data import MarketDataResponse
from app.data.loaders import build_alpaca_data_feed_with_cache
from app.daily_index_forecast.features import build_feature_and_label_records, load_universe_frames
from app.daily_index_forecast.pipeline import build_dataset_frames, train_daily_index_model
from app.daily_index_forecast.models import (
    DailyIndexForecastCreateRequest,
    DailyIndexForecastChartPredictionRowResponse,
    DailyIndexForecastChartResponse,
    DailyIndexForecastDatasetManifestSummary,
    DailyIndexForecastSplitLabel,
)
from app.daily_index_forecast.records import DailyIndexModelArtifact
from app.daily_index_forecast.records import records_to_frame


def _load_model_artifact(model_path: str | None) -> DailyIndexModelArtifact | None:
    if not model_path:
        return None
    path = Path(model_path)
    if not path.is_file():
        return None
    return DailyIndexModelArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def _load_manifest(manifest_path: str | None) -> DailyIndexForecastDatasetManifestSummary | None:
    if not manifest_path:
        return None
    path = Path(manifest_path)
    if not path.is_file():
        return None
    return DailyIndexForecastDatasetManifestSummary.model_validate_json(path.read_text(encoding="utf-8"))


def _build_model_artifact_from_params(
    *,
    model_params: dict[str, Any],
    cache_config,
    group_id: str,
    feature_run_id: str,
    selected_date: date,
) -> tuple[DailyIndexModelArtifact, DailyIndexForecastDatasetManifestSummary, pd.DataFrame]:
    request = _build_request_from_params(model_params, selected_date=selected_date)
    _feature_df, _label_df, joined_df, manifest, feature_columns = build_dataset_frames(
        request.universe,
        request.feature_config,
        request.costs,
        cache_config,
        force_refresh=False,
    )
    artifact, _metrics, _fold_metrics = train_daily_index_model(
        joined_df,
        group_id=group_id,
        feature_run_id=feature_run_id,
        train_config=request.train_config,
        walk_forward=request.walk_forward,
        costs=request.costs,
        feature_columns=feature_columns,
    )
    return artifact, manifest, joined_df


def _load_dataset_frames(manifest: DailyIndexForecastDatasetManifestSummary) -> pd.DataFrame:
    dataset_path = Path(manifest.output_path)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset parquet not found: {dataset_path}")
    return pd.read_parquet(dataset_path)


def _build_request_from_params(params: dict[str, Any], *, selected_date: date) -> DailyIndexForecastCreateRequest:
    universe = dict(params.get("universe") or {})
    if not universe:
        raise ValueError("Model parameters are missing universe configuration")
    universe["end_date"] = selected_date.isoformat()
    if "start_date" in universe:
        start_date = pd.Timestamp(universe["start_date"]).date()
        if selected_date < start_date:
            universe["start_date"] = selected_date.isoformat()
    payload = {
        "name": params.get("name"),
        "universe": universe,
        "feature_config": params.get("feature_config") or {},
        "walk_forward": params.get("walk_forward") or {},
        "train_config": params.get("train_config") or {},
        "costs": params.get("costs") or {},
        "data_cache": params.get("data_cache") or {},
    }
    return DailyIndexForecastCreateRequest.model_validate(payload)


def _bars_from_frame(
    *,
    symbol: str,
    selected_date: date,
    resolution: str,
    frame: pd.DataFrame,
    cache_status: str = "computed",
) -> MarketDataResponse:
    if frame.empty:
        raise ValueError(f"No market bars available for {symbol} on {selected_date.isoformat()}")
    session_mask = pd.to_datetime(frame.index, utc=True, errors="coerce").date == selected_date
    session_frame = frame.loc[session_mask].copy()
    if session_frame.empty:
        raise ValueError(f"No market bars available for {symbol} on {selected_date.isoformat()}")
    bars = MarketDataResponse(
        symbol=symbol,
        provider="alpaca",
        resolution=resolution,
        start_date=selected_date,
        stop_date=selected_date,
        cache_status=cache_status,
        rows=frame_to_rows(session_frame),
    )
    return bars


def _split_label_for_timestamp(
    *,
    decision_timestamp: datetime,
    artifact: DailyIndexModelArtifact,
    metrics: dict[str, Any] | None,
) -> DailyIndexForecastSplitLabel:
    walk_forward = artifact.walk_forward or {}
    holdout_start_text = walk_forward.get("holdout_start")
    holdout_start = None
    if holdout_start_text:
        holdout_start = pd.Timestamp(holdout_start_text)
        if holdout_start.tzinfo is None:
            holdout_start = holdout_start.tz_localize("UTC")
        else:
            holdout_start = holdout_start.tz_convert("UTC")
    ts = pd.Timestamp(decision_timestamp)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    if holdout_start is not None and ts >= holdout_start:
        return "holdout"

    for fold in (metrics or {}).get("fold_metrics", []):
        def _as_utc(value: Any) -> pd.Timestamp:
            ts_value = pd.Timestamp(value)
            return ts_value.tz_localize("UTC") if ts_value.tzinfo is None else ts_value.tz_convert("UTC")

        validation_start = _as_utc(fold["validation_start"])
        validation_end = _as_utc(fold["validation_end"])
        test_start = _as_utc(fold["test_start"])
        test_end = _as_utc(fold["test_end"])
        train_start = _as_utc(fold["train_start"])
        train_end = _as_utc(fold["train_end"])
        if train_start <= ts < train_end:
            return "train"
        if validation_start <= ts < validation_end:
            return "validation"
        if test_start <= ts < test_end:
            return "test"

    return "other"


def build_daily_index_forecast_chart_data(
    *,
    group_id: str,
    selected_date: date,
    resolution: str,
    cache_config,
    model_path: str,
    manifest_path: str,
    model_params: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> DailyIndexForecastChartResponse:
    if model_params is None:
        raise ValueError("Model parameters are required to load chart data")
    request = _build_request_from_params(model_params, selected_date=selected_date)
    artifact = _load_model_artifact(model_path)
    manifest = _load_manifest(manifest_path)
    if artifact is not None and manifest is not None:
        dataset = _load_dataset_frames(manifest)
    else:
        artifact, manifest, dataset = _build_model_artifact_from_params(
            model_params=model_params,
            cache_config=cache_config,
            group_id=group_id,
            feature_run_id="chart-view",
            selected_date=selected_date,
        )

    symbol = dataset["symbol"].iloc[0] if "symbol" in dataset.columns and not dataset.empty else ""
    if not symbol:
        raise ValueError("Dataset does not include a symbol column")

    frames, _benchmark_frame = load_universe_frames(request.universe, cache_config, force_refresh=False)
    source_frame = frames.get(symbol)
    if source_frame is None or source_frame.empty:
        raise ValueError(f"No market bars available for {symbol} on {selected_date.isoformat()}")

    date_mask = pd.to_datetime(dataset["session_date"], errors="coerce").dt.date == selected_date
    day_rows = dataset.loc[date_mask].copy()
    source = "stored"
    if day_rows.empty:
        if model_params is None:
            raise ValueError(f"No prediction rows found for {selected_date.isoformat()}")
        request = _build_request_from_params(model_params, selected_date=selected_date)
        feature_records, _label_records, _manifest = build_feature_and_label_records(
            request.universe,
            request.feature_config,
            request.costs,
            request.data_cache,
            force_refresh=False,
        )
        computed_frame = records_to_frame(feature_records)
        if computed_frame.empty:
            raise ValueError(f"No prediction rows found for {selected_date.isoformat()}")
        computed_frame["session_date"] = pd.to_datetime(computed_frame["session_date"], errors="coerce").dt.date
        day_rows = computed_frame.loc[computed_frame["session_date"] == selected_date].copy()
        if day_rows.empty:
            raise ValueError(f"No prediction rows found for {selected_date.isoformat()}")
        source = "computed"

    rows_by_time = day_rows.sort_values(["decision_timestamp", "decision_time"], kind="mergesort")
    split_label = _split_label_for_timestamp(
        decision_timestamp=pd.Timestamp(rows_by_time.iloc[0]["decision_timestamp"]).to_pydatetime(),
        artifact=artifact,
        metrics=metrics,
    )

    feature_columns = [column for column in artifact.selected_features if column in rows_by_time.columns]
    if not feature_columns:
        raise ValueError("No model feature columns are available for prediction")
    missing_features = [column for column in artifact.selected_features if column not in rows_by_time.columns]
    if missing_features:
        raise ValueError(f"Missing required feature columns: {', '.join(missing_features)}")
    if len(artifact.coefficients) != len(feature_columns):
        raise ValueError("Model coefficients do not match the available feature columns")

    x = rows_by_time[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    predictions = x.to_numpy() @ np.asarray(artifact.coefficients, dtype=float) + float(artifact.intercept)

    label_columns = {column for column in ["return_to_close_bps", "net_return_after_cost_bps", "positive_after_cost"] if column in rows_by_time.columns}
    bars = _bars_from_frame(
        symbol=symbol,
        selected_date=selected_date,
        resolution=resolution,
        frame=source_frame,
        cache_status="computed" if source == "computed" else "stored",
    )

    prediction_rows: list[DailyIndexForecastChartPredictionRowResponse] = []
    for idx, (_, row) in enumerate(rows_by_time.iterrows()):
        current_split = _split_label_for_timestamp(
            decision_timestamp=pd.Timestamp(row["decision_timestamp"]).to_pydatetime(),
            artifact=artifact,
            metrics=metrics,
        )
        prediction_rows.append(
            DailyIndexForecastChartPredictionRowResponse(
                session_date=row["session_date"],
                decision_time=str(row["decision_time"]),
                decision_timestamp=pd.Timestamp(row["decision_timestamp"]).to_pydatetime(),
                predicted_bps=float(predictions[idx]),
                actual_bps=float(row["return_to_close_bps"]) if "return_to_close_bps" in label_columns else None,
                actual_after_cost=bool(row["positive_after_cost"]) if "positive_after_cost" in label_columns else None,
                split_label=current_split,
            )
        )

    return DailyIndexForecastChartResponse(
        group_id=group_id,
        symbol=symbol,
        selected_date=selected_date,
        resolution=resolution,
        cache_status=bars.cache_status,
        source=source,
        bars=bars,
        split_label=split_label,
        predictions=prediction_rows,
    )
