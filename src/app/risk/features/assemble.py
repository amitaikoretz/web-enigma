from __future__ import annotations

import pandas as pd

from app.risk.data.bars import bar_index_at_or_before, history_bars
from app.risk.features import indicators as ind
from app.risk.models import EnrichedCandidate, FeatureSnapshot, RiskDatasetConfig


def _safe_return(close: list[float], lag: int) -> float | None:
    if len(close) <= lag or close[-1 - lag] <= 0:
        return None
    return close[-1] / close[-1 - lag] - 1.0


def _flatten_metadata(metadata: dict) -> dict:
    flat: dict = {}
    for key, value in metadata.items():
        if isinstance(value, (bool, int, float, str)) or value is None:
            flat[f"meta_{key}"] = value
    return flat


def build_feature_snapshot(
    candidate: EnrichedCandidate,
    *,
    frame: pd.DataFrame,
    config: RiskDatasetConfig,
    benchmark_frame: pd.DataFrame | None = None,
) -> FeatureSnapshot:
    decision_idx = bar_index_at_or_before(frame, candidate.timestamp)
    if decision_idx is None:
        return FeatureSnapshot(
            candidate_id=candidate.candidate_id,
            feature_version=config.feature_version,
            feature_timestamp=candidate.timestamp,
            feature_quality_flag="INSUFFICIENT_HISTORY",
            metadata_features=_flatten_metadata(candidate.metadata),
        )

    hist = history_bars(frame, decision_idx)
    if len(hist) < config.min_history_bars:
        return FeatureSnapshot(
            candidate_id=candidate.candidate_id,
            feature_version=config.feature_version,
            feature_timestamp=hist.index[-1].isoformat(),
            feature_quality_flag="INSUFFICIENT_HISTORY",
            metadata_features=_flatten_metadata(candidate.metadata),
        )

    close = hist["Close"].astype(float).tolist()
    high = hist["High"].astype(float).tolist()
    low = hist["Low"].astype(float).tolist()
    volume = hist["Volume"].astype(float).tolist()
    open_ = hist["Open"].astype(float).tolist()

    sma20 = ind.sma(close, 20)
    sma50 = ind.sma(close, 50)
    atr_vals = ind.atr(high, low, close, 14)
    rsi_vals = ind.rsi(close, 14)

    atr_latest = float(atr_vals[-1]) if not pd.isna(atr_vals[-1]) else None
    atr_14_pct = (atr_latest / close[-1]) if atr_latest is not None and close[-1] else None

    tr_window = []
    for i in range(len(close)):
        if i == 0:
            tr_window.append(high[i] - low[i])
        else:
            tr_window.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    atr10 = sum(tr_window[-10:]) / min(10, len(tr_window)) if tr_window else None
    atr50 = sum(tr_window[-50:]) / min(50, len(tr_window)) if tr_window else None
    atr_expansion = (atr10 / atr50) if atr10 and atr50 else None

    dollar_vol = [c * v for c, v in zip(close, volume, strict=False)]
    dollar_volume_20 = float(sum(dollar_vol[-20:]) / min(20, len(dollar_vol))) if dollar_vol else None

    gap_pct = None
    if len(open_) >= 2 and close[-2] > 0:
        gap_pct = open_[-1] / close[-2] - 1.0

    vols: list[float] = []
    for i in range(len(close)):
        vol = ind.realized_vol(close[: i + 1], 20)
        vols.append(vol if vol is not None else float("nan"))
    vol_percentile_60 = ind.percentile_rank_latest(vols, config.vol_percentile_window)

    index_return_20 = None
    index_trend_slope_50 = None
    correlation_to_index_60 = None
    beta_to_index_60 = None

    if config.include_index_features and benchmark_frame is not None:
        bench_idx = bar_index_at_or_before(benchmark_frame, candidate.timestamp)
        if bench_idx is not None:
            bench_hist = history_bars(benchmark_frame, bench_idx)
            bench_close = bench_hist["Close"].astype(float).tolist()
            index_return_20 = _safe_return(bench_close, 20)
            index_trend_slope_50 = ind.log_slope(bench_close, 50)
            correlation_to_index_60, beta_to_index_60 = ind.correlation_beta(close, bench_close, 60)

    return FeatureSnapshot(
        candidate_id=candidate.candidate_id,
        feature_version=config.feature_version,
        feature_timestamp=hist.index[-1].isoformat(),
        feature_quality_flag="OK",
        return_5=_safe_return(close, 5),
        return_10=_safe_return(close, 10),
        return_20=_safe_return(close, 20),
        trend_slope_20=ind.log_slope(close, 20),
        trend_slope_50=ind.log_slope(close, 50),
        sma_20_distance=(close[-1] / sma20[-1] - 1.0) if not pd.isna(sma20[-1]) else None,
        sma_50_distance=(close[-1] / sma50[-1] - 1.0) if not pd.isna(sma50[-1]) else None,
        rsi_14=float(rsi_vals[-1]) if not pd.isna(rsi_vals[-1]) else None,
        return_zscore_20=ind.zscore_latest([close[i] / close[i - 1] - 1.0 for i in range(1, len(close))], 20),
        gap_pct=gap_pct,
        consecutive_up_bars=ind.consecutive_up_bars(close),
        volume_zscore_20=ind.zscore_latest(volume, 20),
        relative_volume_20=(volume[-1] / (sum(volume[-20:]) / min(20, len(volume)))) if volume else None,
        atr_14_pct=atr_14_pct,
        realized_vol_10=ind.realized_vol(close, 10),
        realized_vol_20=ind.realized_vol(close, 20),
        vol_percentile_60=vol_percentile_60,
        atr_expansion_10_50=atr_expansion,
        dollar_volume_20=dollar_volume_20,
        volume_percentile_60=ind.percentile_rank_latest(volume, config.vol_percentile_window),
        index_return_20=index_return_20,
        index_trend_slope_50=index_trend_slope_50,
        correlation_to_index_60=correlation_to_index_60,
        beta_to_index_60=beta_to_index_60,
        metadata_features=_flatten_metadata(candidate.metadata),
    )
