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
    DailyIndexUniverseConfig,
)
from app.daily_index_forecast.records import DailyIndexModelArtifact
from app.daily_index_forecast.records import records_to_frame


def _as_utc_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def resolve_artifact_path(path_str: str | None) -> Path | None:
    if not path_str:
        return None

    candidate = Path(path_str)
    search_paths = [candidate]
    repo_root = Path(__file__).resolve().parents[3]

    if candidate.is_absolute():
        if len(candidate.parts) > 2 and candidate.parts[1] == "data":
            relative_path = Path(*candidate.parts[2:])
            search_paths.extend(
                [
                    repo_root / "data" / relative_path,
                    Path.cwd() / "data" / relative_path,
                ]
            )
    else:
        search_paths.extend([Path.cwd() / candidate, repo_root / candidate])

    for path in search_paths:
        try:
            if path.is_file() or path.is_dir():
                return path
        except OSError:
            continue
    return None


def _load_model_artifact(model_path: str | None) -> DailyIndexModelArtifact | None:
    path = resolve_artifact_path(model_path)
    if path is None:
        return None
    return DailyIndexModelArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def _load_manifest(manifest_path: str | None) -> DailyIndexForecastDatasetManifestSummary | None:
    path = resolve_artifact_path(manifest_path)
    if path is None:
        return None
    return DailyIndexForecastDatasetManifestSummary.model_validate_json(path.read_text(encoding="utf-8"))


def resolve_holdout_session_dates_from_dataset(
    dataset: pd.DataFrame,
    artifact: DailyIndexModelArtifact,
) -> list[date]:
    walk_forward = artifact.walk_forward or {}
    holdout_start_text = walk_forward.get("holdout_start")
    if not holdout_start_text or dataset.empty:
        return []

    if "session_date" not in dataset.columns or "decision_timestamp" not in dataset.columns:
        return []

    holdout_start = _as_utc_timestamp(holdout_start_text)
    decision_ts = pd.to_datetime(dataset["decision_timestamp"], utc=True, errors="coerce")
    session_dates = pd.to_datetime(dataset["session_date"], errors="coerce").dt.date
    if decision_ts.isna().any() or session_dates.isna().any():
        raise ValueError("Dataset contains invalid session or decision timestamps")

    holdout_mask = decision_ts >= holdout_start
    return sorted({session_date for session_date in session_dates.loc[holdout_mask].tolist() if session_date is not None})


def resolve_holdout_session_dates(
    *,
    model_path: str | None,
    manifest_path: str | None,
) -> list[date]:
    artifact = _load_model_artifact(model_path)
    manifest = _load_manifest(manifest_path)
    if artifact is None or manifest is None:
        return []
    dataset = _load_dataset_frames(manifest)
    return resolve_holdout_session_dates_from_dataset(dataset, artifact)


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
    dataset_path = resolve_artifact_path(manifest.output_path)
    if dataset_path is None:
        raise FileNotFoundError(f"Dataset parquet not found: {manifest.output_path}")
    return pd.read_parquet(dataset_path)


def _build_chart_universe(universe: DailyIndexUniverseConfig, selected_date: date) -> DailyIndexUniverseConfig:
    payload = universe.model_dump(mode="json")
    payload["start_date"] = selected_date.isoformat()
    payload["end_date"] = selected_date.isoformat()
    return DailyIndexUniverseConfig.model_validate(payload)


def _predict_with_artifact(
    *,
    artifact: DailyIndexModelArtifact,
    rows: pd.DataFrame,
    feature_columns: list[str],
) -> np.ndarray:
    x = rows[feature_columns].replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    values = x.to_numpy(dtype=float)

    if artifact.scaler_mean and artifact.scaler_scale:
        if len(artifact.scaler_mean) != len(feature_columns) or len(artifact.scaler_scale) != len(feature_columns):
            raise ValueError("Model scaler values do not match the available feature columns")
        mean = np.asarray(artifact.scaler_mean, dtype=float)
        scale = np.asarray(artifact.scaler_scale, dtype=float)
        scale = np.where(scale == 0.0, 1.0, scale)
        values = (values - mean) / scale

    if len(artifact.coefficients) != len(feature_columns):
        raise ValueError("Model coefficients do not match the available feature columns")

    coefficients = np.asarray(artifact.coefficients, dtype=float)
    return values @ coefficients + float(artifact.intercept)


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

    holdout_dates = resolve_holdout_session_dates_from_dataset(dataset, artifact)
    if selected_date not in holdout_dates:
        if holdout_dates:
            allowed = ", ".join(allowed_date.isoformat() for allowed_date in holdout_dates)
            raise ValueError(
                f"Selected date {selected_date.isoformat()} is not one of the holdout days: {allowed}"
            )
        raise ValueError("No holdout dates are available for chart selection")

    symbol = dataset["symbol"].iloc[0] if "symbol" in dataset.columns and not dataset.empty else ""
    if not symbol:
        raise ValueError("Dataset does not include a symbol column")

    chart_universe = _build_chart_universe(request.universe, selected_date)
    frames, _benchmark_frame = load_universe_frames(chart_universe, cache_config, force_refresh=False)
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
    predictions = _predict_with_artifact(artifact=artifact, rows=rows_by_time, feature_columns=feature_columns)

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
