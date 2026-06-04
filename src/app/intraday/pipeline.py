from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.preprocessing import StandardScaler

from app.config.models import AlpacaDataSource, CsvDataSource, DataCacheConfig, YahooDataSource
from app.data.loaders import build_alpaca_data_feed_with_cache, build_csv_data_feed, build_yahoo_data_feed_with_cache
from app.intraday.features import FEATURE_COLUMNS, build_intraday_rows, resolve_date_buffer_days, rows_to_frame
from app.intraday.models import (
    ForecastDirection,
    IntradayCostConfig,
    IntradayDatasetManifest,
    IntradayModelArtifact,
    IntradayRunConfig,
    IntradayRunMetrics,
    IntradaySizingConfig,
    PositionSizingDecision,
)
from app.intraday.walk_forward import make_walk_forward_folds, resolve_walk_forward_config


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)


def _config_hash(config: IntradayRunConfig) -> str:
    payload = config.model_dump(mode="json")
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _roundtrip_cost_bps(costs: IntradayCostConfig) -> float:
    return costs.roundtrip_bps


def _ensure_utc_index(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.index = pd.to_datetime(out.index, utc=True, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    return out


def _resolve_source_data(
    source: CsvDataSource | YahooDataSource | AlpacaDataSource,
    *,
    start_date,
    end_date,
    cache_config: DataCacheConfig,
    force_refresh: bool = False,
) -> pd.DataFrame:
    if isinstance(source, CsvDataSource):
        return build_csv_data_feed(source, start_date, end_date)
    if isinstance(source, YahooDataSource):
        frame, _ = build_yahoo_data_feed_with_cache(
            source,
            start_date,
            end_date,
            cache_config=cache_config,
            force_refresh=force_refresh,
        )
        return frame
    if isinstance(source, AlpacaDataSource):
        frame, _ = build_alpaca_data_feed_with_cache(
            source,
            start_date,
            end_date,
            cache_config=cache_config,
            force_refresh=force_refresh,
        )
        return frame
    raise TypeError(f"Unsupported data source type: {type(source)!r}")


def load_intraday_frames(
    config: IntradayRunConfig,
    *,
    force_refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame | None]:
    buffer_days = resolve_date_buffer_days(config.universe.interval, config.lookback_bars, config.horizon_bars)
    start_date = pd.Timestamp(config.universe.start_date) - pd.Timedelta(days=buffer_days)
    end_date = pd.Timestamp(config.universe.end_date) + pd.Timedelta(days=buffer_days)

    frames: dict[str, pd.DataFrame] = {}
    for spec in config.universe.symbols:
        symbol = spec.symbol or getattr(spec.data, "symbol", None)
        if not symbol:
            raise ValueError("Each intraday symbol spec requires a symbol")
        frame = _resolve_source_data(
            spec.data,
            start_date=start_date.date(),
            end_date=end_date.date(),
            cache_config=config.data_cache,
            force_refresh=force_refresh,
        )
        frames[symbol] = _ensure_utc_index(frame)

    benchmark_frame: pd.DataFrame | None = None
    if config.universe.benchmark is not None:
        benchmark_frame = _resolve_source_data(
            config.universe.benchmark.data,
            start_date=start_date.date(),
            end_date=end_date.date(),
            cache_config=config.data_cache,
            force_refresh=force_refresh,
        )
        benchmark_frame = _ensure_utc_index(benchmark_frame)
    return frames, benchmark_frame


def build_intraday_dataset(
    config: IntradayRunConfig,
    *,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, IntradayDatasetManifest]:
    frames, benchmark_frame = load_intraday_frames(config, force_refresh=force_refresh)
    rows = []
    total_history_rows = 0
    total_forward_rows = 0
    for spec in config.universe.symbols:
        symbol = spec.symbol or getattr(spec.data, "symbol", None)
        if not symbol:
            raise ValueError("Each intraday symbol spec requires a symbol")
        frame = frames[symbol]
        per_symbol_rows = build_intraday_rows(
            frame,
            symbol=symbol,
            horizon_bars=config.horizon_bars,
            benchmark_frame=benchmark_frame,
            lookback_bars=config.lookback_bars,
        )
        total_history_rows += min(len(frame), config.lookback_bars)
        total_forward_rows += min(max(0, len(frame) - config.lookback_bars), config.horizon_bars)
        rows.extend(per_symbol_rows)

    dataset = rows_to_frame(rows)
    if dataset.empty:
        raise ValueError("No intraday training rows could be built from the provided universe")

    dataset = dataset.sort_values(["timestamp", "symbol"], kind="mergesort").reset_index(drop=True)
    manifest = IntradayDatasetManifest(
        generated_at=datetime.now(UTC),
        dataset_version=config.dataset_version,
        feature_version=config.feature_version,
        label_version=config.label_version,
        model_version=config.model_version,
        config_hash=_config_hash(config),
        symbol_count=len(frames),
        benchmark_symbol=config.universe.benchmark.symbol if config.universe.benchmark is not None else None,
        start_date=config.universe.start_date,
        end_date=config.universe.end_date,
        total_rows=int(sum(len(frame) for frame in frames.values())),
        kept_rows=int(len(dataset)),
        dropped_history_rows=int(total_history_rows),
        dropped_forward_rows=int(total_forward_rows),
        feature_columns=FEATURE_COLUMNS,
        dataset_path="",
        predictions_path="",
        positions_path="",
        model_path="",
        metrics_path="",
    )
    return dataset, manifest


def _select_feature_columns(df: pd.DataFrame) -> list[str]:
    cols = [col for col in FEATURE_COLUMNS if col in df.columns]
    return cols


def _metric_mean(values: list[float | None]) -> float | None:
    valid = [value for value in values if value is not None]
    if not valid:
        return None
    return float(np.mean(valid))


def _positive_signal(direction_value: float) -> ForecastDirection:
    if direction_value > 0:
        return "LONG"
    if direction_value < 0:
        return "SHORT"
    return "FLAT"


def _fit_model(x_train: pd.DataFrame, y_train: np.ndarray, alpha: float) -> tuple[StandardScaler, Ridge]:
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_train)
    model = Ridge(alpha=alpha)
    model.fit(x_scaled, y_train)
    return scaler, model


def _predict(scaler: StandardScaler, model: Ridge, x: pd.DataFrame) -> np.ndarray:
    return np.asarray(model.predict(scaler.transform(x)), dtype=float)


def _quantile_prediction(pred: np.ndarray, residual_std: float, q: float) -> np.ndarray:
    z = {0.1: -1.281551565545, 0.5: 0.0, 0.9: 1.281551565545}.get(q, 0.0)
    return pred + z * residual_std


def _size_position(
    *,
    row: pd.Series,
    expected_edge_bps: float,
    forecast_risk_bps: float,
    threshold_bps: float,
    target_edge_bps: float,
    sizing: IntradaySizingConfig,
    costs: IntradayCostConfig,
    max_risk_fraction: float,
    allow_short: bool,
    fold_id: int | None = None,
) -> PositionSizingDecision:
    direction = _positive_signal(expected_edge_bps)
    if direction == "SHORT" and not allow_short:
        direction = "FLAT"
    if direction == "FLAT" or abs(expected_edge_bps) <= threshold_bps:
        return PositionSizingDecision(
            symbol=str(row["symbol"]),
            timestamp=pd.Timestamp(row["timestamp"]).isoformat(),
            direction="FLAT",
            expected_edge_bps=float(expected_edge_bps),
            forecast_risk_bps=float(forecast_risk_bps),
            threshold_bps=float(threshold_bps),
            quality_scale=0.0,
            vol_scale=0.0,
            risk_based_shares=0.0,
            liquidity_cap_shares=0.0,
            final_shares=0.0,
            final_notional=0.0,
            entry_price=float(row["entry_price"]),
            stop_distance_bps=max(sizing.min_stop_bps, forecast_risk_bps * sizing.stop_vol_multiplier),
            roundtrip_cost_bps=_roundtrip_cost_bps(costs),
            fold_id=fold_id,
            reason="below_threshold",
        )

    entry_price = float(row["entry_price"])
    volume_1 = float(row.get("volume_1", 0.0) or 0.0)
    dollar_volume_20 = float(row.get("dollar_volume_20", 0.0) or 0.0)
    stop_distance_bps = max(sizing.min_stop_bps, forecast_risk_bps * sizing.stop_vol_multiplier)
    stop_distance_pct = stop_distance_bps / 10000.0
    desired_risk_dollars = max_risk_fraction * sizing.account_equity
    if entry_price <= 0 or stop_distance_pct <= 0:
        return PositionSizingDecision(
            symbol=str(row["symbol"]),
            timestamp=pd.Timestamp(row["timestamp"]).isoformat(),
            direction=direction,
            expected_edge_bps=float(expected_edge_bps),
            forecast_risk_bps=float(forecast_risk_bps),
            threshold_bps=float(threshold_bps),
            quality_scale=0.0,
            vol_scale=0.0,
            risk_based_shares=0.0,
            liquidity_cap_shares=0.0,
            final_shares=0.0,
            final_notional=0.0,
            entry_price=entry_price,
            stop_distance_bps=stop_distance_bps,
            roundtrip_cost_bps=_roundtrip_cost_bps(costs),
            fold_id=fold_id,
            reason="bad_price_or_stop",
        )

    risk_based_shares = desired_risk_dollars / (entry_price * stop_distance_pct)
    quality_scale = float(np.clip((abs(expected_edge_bps) - threshold_bps) / max(target_edge_bps, 1e-9), 0.0, 1.0))
    vol_scale = float(np.clip(sizing.target_vol_bps / max(forecast_risk_bps, sizing.floor_vol_bps), 0.0, 5.0))
    liquidity_cap_by_volume = sizing.max_participation_rate * volume_1
    liquidity_cap_by_notional = (sizing.max_notional_fraction * dollar_volume_20 / entry_price) if dollar_volume_20 > 0 else liquidity_cap_by_volume
    liquidity_cap_shares = max(0.0, min(liquidity_cap_by_volume, liquidity_cap_by_notional))
    final_shares = max(0.0, min(risk_based_shares * quality_scale * vol_scale, liquidity_cap_shares))
    final_shares = float(final_shares if direction == "LONG" else -final_shares)
    final_notional = float(abs(final_shares) * entry_price)

    return PositionSizingDecision(
        symbol=str(row["symbol"]),
        timestamp=pd.Timestamp(row["timestamp"]).isoformat(),
        direction=direction,
        expected_edge_bps=float(expected_edge_bps),
        forecast_risk_bps=float(forecast_risk_bps),
        threshold_bps=float(threshold_bps),
        quality_scale=quality_scale,
        vol_scale=vol_scale,
        risk_based_shares=float(risk_based_shares),
        liquidity_cap_shares=float(liquidity_cap_shares),
        final_shares=final_shares,
        final_notional=final_notional,
        entry_price=entry_price,
        stop_distance_bps=stop_distance_bps,
        roundtrip_cost_bps=_roundtrip_cost_bps(costs),
        fold_id=fold_id,
        reason="active_signal",
    )


def _evaluate_predictions(
    df: pd.DataFrame,
    *,
    pred_return_pct: np.ndarray,
    residual_std: float,
    fold_id: int,
    subset: str,
    threshold_bps: float,
    target_edge_bps: float,
    sizing: IntradaySizingConfig,
    costs: IntradayCostConfig,
    max_risk_fraction: float,
    allow_short: bool,
) -> tuple[pd.DataFrame, list[PositionSizingDecision], dict[str, float | None]]:
    output = df.copy().reset_index(drop=True)
    output["fold_id"] = fold_id
    output["subset"] = subset
    output["pred_return_pct"] = pred_return_pct
    output["pred_return_bps"] = output["pred_return_pct"] * 10000.0
    output["pred_vol_bps"] = residual_std * 10000.0
    output["pred_quantile_10_pct"] = _quantile_prediction(pred_return_pct, residual_std, 0.1)
    output["pred_quantile_50_pct"] = _quantile_prediction(pred_return_pct, residual_std, 0.5)
    output["pred_quantile_90_pct"] = _quantile_prediction(pred_return_pct, residual_std, 0.9)
    output["expected_edge_bps"] = output["pred_return_bps"] - _roundtrip_cost_bps(costs)
    output["forecast_risk_bps"] = np.maximum(output["pred_vol_bps"], sizing.floor_vol_bps)

    decisions: list[PositionSizingDecision] = []
    for _, row in output.iterrows():
        decisions.append(
            _size_position(
                row=row,
                expected_edge_bps=float(row["expected_edge_bps"]),
                forecast_risk_bps=float(row["forecast_risk_bps"]),
                threshold_bps=float(threshold_bps),
                target_edge_bps=float(target_edge_bps),
                sizing=sizing,
                costs=costs,
                max_risk_fraction=max_risk_fraction,
                allow_short=allow_short,
                fold_id=fold_id,
            )
        )

    positions = pd.DataFrame([d.model_dump(mode="json") for d in decisions])
    output["direction"] = positions["direction"]
    output["final_shares"] = positions["final_shares"]
    output["final_notional"] = positions["final_notional"]
    output["stop_distance_bps"] = positions["stop_distance_bps"]
    output["quality_scale"] = positions["quality_scale"]
    output["vol_scale"] = positions["vol_scale"]
    output["liquidity_cap_shares"] = positions["liquidity_cap_shares"]

    signal_sign = np.sign(output["final_shares"]).fillna(0.0)
    realized_return_pct = output["target_return_pct"] * signal_sign
    gross_pnl = output["final_notional"] * realized_return_pct
    roundtrip_cost = output["final_notional"] * (_roundtrip_cost_bps(costs) / 10000.0)
    net_pnl = gross_pnl - roundtrip_cost
    output["gross_pnl"] = gross_pnl
    output["roundtrip_cost"] = roundtrip_cost
    output["net_pnl"] = net_pnl
    output["realized_gross_pnl"] = output["final_notional"] * output["target_return_pct"]
    output["realized_net_pnl"] = output["realized_gross_pnl"] - roundtrip_cost
    output["hit_direction"] = np.sign(output["pred_return_pct"]) == np.sign(output["target_return_pct"])

    metrics = {
        "rows": float(len(output)),
        "gross_pnl": float(output["gross_pnl"].sum()),
        "net_pnl": float(output["net_pnl"].sum()),
        "realized_gross_pnl": float(output["realized_gross_pnl"].sum()),
        "realized_net_pnl": float(output["realized_net_pnl"].sum()),
        "hit_rate": float(output["hit_direction"].mean()) if len(output) else None,
        "mae": float(mean_absolute_error(output["target_return_pct"], output["pred_return_pct"])) if len(output) else None,
        "rmse": float(np.sqrt(mean_squared_error(output["target_return_pct"], output["pred_return_pct"]))) if len(output) else None,
        "sharpe": float(output["net_pnl"].mean() / output["net_pnl"].std(ddof=0)) if len(output) > 1 and output["net_pnl"].std(ddof=0) else None,
        "max_drawdown": _max_drawdown(output["net_pnl"]),
    }

    return output, decisions, metrics


def _max_drawdown(values: pd.Series) -> float | None:
    if values.empty:
        return None
    equity = values.cumsum()
    running_max = equity.cummax()
    drawdown = equity - running_max
    return float(drawdown.min())


def _aggregate_metrics(fold_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "validation": {
            "net_pnl_sum": _metric_mean([m["validation"].get("net_pnl") for m in fold_metrics]),
            "gross_pnl_sum": _metric_mean([m["validation"].get("gross_pnl") for m in fold_metrics]),
            "hit_rate": _metric_mean([m["validation"].get("hit_rate") for m in fold_metrics]),
            "mae": _metric_mean([m["validation"].get("mae") for m in fold_metrics]),
            "rmse": _metric_mean([m["validation"].get("rmse") for m in fold_metrics]),
            "sharpe": _metric_mean([m["validation"].get("sharpe") for m in fold_metrics]),
        },
        "test": {
            "net_pnl_sum": _metric_mean([m["test"].get("net_pnl") for m in fold_metrics]),
            "gross_pnl_sum": _metric_mean([m["test"].get("gross_pnl") for m in fold_metrics]),
            "hit_rate": _metric_mean([m["test"].get("hit_rate") for m in fold_metrics]),
            "mae": _metric_mean([m["test"].get("mae") for m in fold_metrics]),
            "rmse": _metric_mean([m["test"].get("rmse") for m in fold_metrics]),
            "sharpe": _metric_mean([m["test"].get("sharpe") for m in fold_metrics]),
        },
    }


def run_intraday_pipeline(
    config: IntradayRunConfig,
    *,
    force_refresh: bool = False,
) -> dict[str, Any]:
    dataset, manifest = build_intraday_dataset(config, force_refresh=force_refresh)
    feature_cols = _select_feature_columns(dataset)
    if not feature_cols:
        raise ValueError("No numeric intraday features were available")

    walk_forward_cfg = resolve_walk_forward_config(
        dataset,
        {
            "timestamp_column": "timestamp",
            "train_days": config.walk_forward.train_days,
            "validation_days": config.walk_forward.validation_days,
            "test_days": config.walk_forward.test_days,
            "step_days": config.walk_forward.step_days,
            "embargo_bars": config.walk_forward.embargo_bars,
            "min_train_rows": config.walk_forward.min_train_rows,
            "min_validation_rows": config.walk_forward.min_validation_rows,
            "min_test_rows": config.walk_forward.min_test_rows,
        },
    )
    folds = make_walk_forward_folds(dataset, walk_forward_cfg)
    if not folds:
        raise ValueError("No walk-forward folds could be built from the dataset")

    X_all = dataset[feature_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0).astype(float)
    y_all = dataset["target_return_pct"].astype(float).to_numpy()
    ts_all = pd.to_datetime(dataset["timestamp"], utc=True, errors="coerce")

    fold_metrics: list[dict[str, Any]] = []
    prediction_frames: list[pd.DataFrame] = []
    position_frames: list[pd.DataFrame] = []
    selected_hyperparams: dict[str, float] = {}
    final_model_artifact: IntradayModelArtifact | None = None
    final_scaler: StandardScaler | None = None
    final_model: Ridge | None = None
    final_residual_std = 0.0

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

        best_combo: dict[str, float] | None = None
        best_validation_score = -np.inf

        for alpha in config.model_search.alpha_grid:
            scaler, model = _fit_model(x_train, y_train, alpha=float(alpha))
            p_validation = _predict(scaler, model, x_validation)
            residuals = y_validation - p_validation
            residual_std = float(np.std(residuals, ddof=0)) if len(residuals) else 0.0
            for threshold_bps in config.model_search.threshold_bps_grid:
                for target_edge_bps in config.model_search.target_edge_bps_grid:
                    for max_risk_fraction in config.model_search.max_risk_fraction_grid:
                        _, _, validation_metrics = _evaluate_predictions(
                            dataset.loc[validation_mask].copy(),
                            pred_return_pct=p_validation,
                            residual_std=residual_std,
                            fold_id=fold.fold_id,
                            subset="validation",
                            threshold_bps=float(threshold_bps),
                            target_edge_bps=float(target_edge_bps),
                            sizing=config.sizing,
                            costs=config.costs,
                            max_risk_fraction=float(max_risk_fraction),
                            allow_short=config.allow_short,
                        )
                        score = float(validation_metrics["net_pnl"] or 0.0)
                        if score > best_validation_score:
                            best_validation_score = score
                            best_combo = {
                                "alpha": float(alpha),
                                "threshold_bps": float(threshold_bps),
                                "target_edge_bps": float(target_edge_bps),
                                "max_risk_fraction": float(max_risk_fraction),
                            }

        if best_combo is None:
            raise ValueError(f"Could not select hyperparameters for fold {fold.fold_id}")

        selected_hyperparams = best_combo
        best_scaler, best_model = _fit_model(x_train, y_train, alpha=best_combo["alpha"])
        best_validation_preds = _predict(best_scaler, best_model, x_validation)
        best_validation_residual_std = float(np.std(y_validation - best_validation_preds, ddof=0)) if len(y_validation) else 0.0
        validation_eval, validation_decisions, validation_eval_metrics = _evaluate_predictions(
            dataset.loc[validation_mask].copy(),
            pred_return_pct=best_validation_preds,
            residual_std=best_validation_residual_std,
            fold_id=fold.fold_id,
            subset="validation",
            threshold_bps=best_combo["threshold_bps"],
            target_edge_bps=best_combo["target_edge_bps"],
            sizing=config.sizing,
            costs=config.costs,
            max_risk_fraction=best_combo["max_risk_fraction"],
            allow_short=config.allow_short,
        )

        train_plus_validation_mask = (ts_all >= fold.train_start) & (ts_all < fold.validation_end)
        x_train_plus_validation = X_all.loc[train_plus_validation_mask]
        y_train_plus_validation = y_all[train_plus_validation_mask.to_numpy()]
        final_scaler, final_model = _fit_model(x_train_plus_validation, y_train_plus_validation, alpha=best_combo["alpha"])
        final_residual_std = float(
            np.std(y_train_plus_validation - _predict(final_scaler, final_model, x_train_plus_validation), ddof=0)
        )

        p_test = _predict(final_scaler, final_model, x_test)
        test_df, decisions, test_metrics = _evaluate_predictions(
            dataset.loc[test_mask].copy(),
            pred_return_pct=p_test,
            residual_std=final_residual_std,
            fold_id=fold.fold_id,
            subset="test",
            threshold_bps=best_combo["threshold_bps"],
            target_edge_bps=best_combo["target_edge_bps"],
            sizing=config.sizing,
            costs=config.costs,
            max_risk_fraction=best_combo["max_risk_fraction"],
            allow_short=config.allow_short,
        )

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
                "selected_hyperparameters": best_combo,
                "validation": validation_eval_metrics,
                "test": test_metrics,
            }
        )

        prediction_frames.extend([validation_eval, test_df])
        position_frames.extend(
            [
                pd.DataFrame([d.model_dump(mode="json") for d in validation_decisions]),
                pd.DataFrame([d.model_dump(mode="json") for d in decisions]),
            ]
        )

        final_model_artifact = IntradayModelArtifact(
            model_version=config.model_version,
            feature_version=config.feature_version,
            label_version=config.label_version,
            dataset_version=config.dataset_version,
            fold_id=fold.fold_id,
            selected_features=feature_cols,
            scaler_mean=final_scaler.mean_.tolist() if final_scaler is not None else [],
            scaler_scale=final_scaler.scale_.tolist() if final_scaler is not None else [],
            coefficients=final_model.coef_.tolist() if final_model is not None else [],
            intercept=float(final_model.intercept_) if final_model is not None else 0.0,
            residual_std=float(final_residual_std),
            walk_forward={
                "timestamp_column": "timestamp",
                "train_days": walk_forward_cfg.train_days,
                "validation_days": walk_forward_cfg.validation_days,
                "test_days": walk_forward_cfg.test_days,
                "step_days": walk_forward_cfg.step_days,
                "embargo_bars": walk_forward_cfg.embargo_bars,
                "n_folds": len(folds),
            },
            costs={
                "spread_bps": config.costs.spread_bps,
                "slippage_bps": config.costs.slippage_bps,
                "impact_bps": config.costs.impact_bps,
                "roundtrip_bps": _roundtrip_cost_bps(config.costs),
            },
            sizing={
                "account_equity": config.sizing.account_equity,
                "max_participation_rate": config.sizing.max_participation_rate,
                "max_notional_fraction": config.sizing.max_notional_fraction,
                "target_vol_bps": config.sizing.target_vol_bps,
                "floor_vol_bps": config.sizing.floor_vol_bps,
                "stop_vol_multiplier": config.sizing.stop_vol_multiplier,
                "min_stop_bps": config.sizing.min_stop_bps,
            },
            selected_hyperparameters=best_combo,
            validation_metrics=validation_eval_metrics,
            test_metrics=test_metrics,
        )

    predictions = pd.concat(prediction_frames, ignore_index=True) if prediction_frames else pd.DataFrame()
    positions = pd.concat(position_frames, ignore_index=True) if position_frames else pd.DataFrame()

    aggregate = {
        "validation": {
            "net_pnl_mean": _metric_mean([m["validation"].get("net_pnl") for m in fold_metrics]),
            "gross_pnl_mean": _metric_mean([m["validation"].get("gross_pnl") for m in fold_metrics]),
            "hit_rate_mean": _metric_mean([m["validation"].get("hit_rate") for m in fold_metrics]),
            "mae_mean": _metric_mean([m["validation"].get("mae") for m in fold_metrics]),
            "rmse_mean": _metric_mean([m["validation"].get("rmse") for m in fold_metrics]),
            "sharpe_mean": _metric_mean([m["validation"].get("sharpe") for m in fold_metrics]),
        },
        "test": {
            "net_pnl_mean": _metric_mean([m["test"].get("net_pnl") for m in fold_metrics]),
            "gross_pnl_mean": _metric_mean([m["test"].get("gross_pnl") for m in fold_metrics]),
            "hit_rate_mean": _metric_mean([m["test"].get("hit_rate") for m in fold_metrics]),
            "mae_mean": _metric_mean([m["test"].get("mae") for m in fold_metrics]),
            "rmse_mean": _metric_mean([m["test"].get("rmse") for m in fold_metrics]),
            "sharpe_mean": _metric_mean([m["test"].get("sharpe") for m in fold_metrics]),
        },
        "selected_hyperparameters": selected_hyperparams,
    }

    metrics = IntradayRunMetrics(
        generated_at=datetime.now(UTC),
        dataset_version=config.dataset_version,
        feature_version=config.feature_version,
        label_version=config.label_version,
        model_version=config.model_version,
        config_hash=_config_hash(config),
        selected_hyperparameters=selected_hyperparams,
        fold_metrics=fold_metrics,
        aggregate=aggregate,
    )

    manifest.dataset_path = ""
    manifest.predictions_path = ""
    manifest.positions_path = ""
    manifest.model_path = ""
    manifest.metrics_path = ""

    return {
        "dataset": dataset,
        "manifest": manifest,
        "predictions": predictions,
        "positions": positions,
        "model": final_model_artifact,
        "metrics": metrics,
    }


def write_intraday_artifacts(result: dict[str, Any], output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = output_dir / "dataset.parquet"
    manifest_path = output_dir / "manifest.json"
    predictions_path = output_dir / "predictions.parquet"
    positions_path = output_dir / "positions.parquet"
    model_path = output_dir / "model.json"
    metrics_path = output_dir / "metrics.json"

    result["dataset"].to_parquet(dataset_path, index=False)
    result["predictions"].to_parquet(predictions_path, index=False)
    result["positions"].to_parquet(positions_path, index=False)
    model_json = result["model"].model_dump(mode="json") if result.get("model") is not None else {}
    metrics_json = result["metrics"].model_dump(mode="json")
    manifest = result["manifest"].model_copy(
        update={
            "dataset_path": str(dataset_path),
            "predictions_path": str(predictions_path),
            "positions_path": str(positions_path),
            "model_path": str(model_path),
            "metrics_path": str(metrics_path),
        }
    )
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json"), indent=2, default=_json_default), encoding="utf-8")
    model_path.write_text(json.dumps(model_json, indent=2, default=_json_default), encoding="utf-8")
    metrics_path.write_text(json.dumps(metrics_json, indent=2, default=_json_default), encoding="utf-8")
    return {
        "dataset": dataset_path,
        "manifest": manifest_path,
        "predictions": predictions_path,
        "positions": positions_path,
        "model": model_path,
        "metrics": metrics_path,
    }
