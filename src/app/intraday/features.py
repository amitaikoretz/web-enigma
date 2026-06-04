from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil
from typing import Any

import numpy as np
import pandas as pd

from app.risk.features import indicators as ind
from app.risk.data.bars import interval_duration

FEATURE_COLUMNS: list[str] = [
    "ret_1",
    "ret_5",
    "ret_20",
    "ret_z_20",
    "range_pct_1",
    "close_to_high_pct",
    "close_to_low_pct",
    "sma_20_dist",
    "ema_9_dist",
    "trend_slope_20",
    "rsi_14",
    "consecutive_up_bars",
    "volume_1",
    "volume_z_20",
    "relative_volume_20",
    "realized_vol_10",
    "realized_vol_20",
    "atr_pct_14",
    "vol_expansion_20_60",
    "time_of_day_sin",
    "time_of_day_cos",
    "minute_of_session",
    "day_of_week",
    "benchmark_ret_5",
    "benchmark_ret_20",
    "benchmark_trend_slope_20",
    "benchmark_realized_vol_20",
    "relative_ret_20",
    "correlation_to_benchmark_20",
    "beta_to_benchmark_20",
]


@dataclass(frozen=True)
class FeatureRow:
    symbol: str
    timestamp: pd.Timestamp
    entry_price: float
    target_return_pct: float
    target_return_bps: float
    features: dict[str, float | None]
    quality_flag: str


def _to_utc_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _safe_log_return(values: Sequence[float], lag: int) -> float | None:
    arr = np.asarray(values, dtype=float)
    if arr.size <= lag:
        return None
    if arr[-1] <= 0 or arr[-1 - lag] <= 0:
        return None
    return float(np.log(arr[-1] / arr[-1 - lag]))


def _safe_pct_return(values: Sequence[float], lag: int) -> float | None:
    arr = np.asarray(values, dtype=float)
    if arr.size <= lag or arr[-1 - lag] == 0:
        return None
    return float(arr[-1] / arr[-1 - lag] - 1.0)


def _safe_distance(close: Sequence[float], series: np.ndarray) -> float | None:
    if series.size == 0 or np.isnan(series[-1]):
        return None
    if close[-1] == 0:
        return None
    return float(close[-1] / series[-1] - 1.0)


def _session_minutes(ts: pd.Timestamp) -> int:
    ts = _to_utc_timestamp(ts)
    ts_local = ts.tz_convert("America/New_York")
    session_open = ts_local.normalize() + pd.Timedelta(hours=9, minutes=30)
    return int((ts_local - session_open).total_seconds() // 60)


def _cyclical_time_features(ts: pd.Timestamp) -> tuple[float, float, int, int]:
    ts = _to_utc_timestamp(ts)
    ts_local = ts.tz_convert("America/New_York")
    minute_of_day = ts_local.hour * 60 + ts_local.minute
    minute_of_session = _session_minutes(ts)
    angle = 2.0 * np.pi * (minute_of_day / (24 * 60))
    return float(np.sin(angle)), float(np.cos(angle)), minute_of_session, int(ts_local.day_of_week)


def _build_feature_dict(hist: pd.DataFrame, benchmark_hist: pd.DataFrame | None = None) -> dict[str, float | None]:
    close = hist["Close"].astype(float).to_list()
    high = hist["High"].astype(float).to_list()
    low = hist["Low"].astype(float).to_list()
    volume = hist["Volume"].astype(float).to_list()

    sma20 = ind.sma(close, 20)
    ema9 = pd.Series(close, dtype=float).ewm(span=9, adjust=False).mean().to_numpy()
    rsi14 = ind.rsi(close, 14)
    atr14 = ind.atr(high, low, close, 14)

    log_returns = []
    for i in range(1, len(close)):
        prev = close[i - 1]
        curr = close[i]
        if prev > 0 and curr > 0:
            log_returns.append(float(np.log(curr / prev)))
        else:
            log_returns.append(np.nan)
    log_returns_arr = np.asarray(log_returns, dtype=float)

    realized_vol_10 = ind.realized_vol(close, 10)
    realized_vol_20 = ind.realized_vol(close, 20)
    vol_60 = ind.realized_vol(close, 60)
    vol_expansion_20_60 = (realized_vol_20 / vol_60) if realized_vol_20 is not None and vol_60 not in (None, 0) else None

    ret_5 = _safe_log_return(close, 5)
    ret_20 = _safe_log_return(close, 20)

    benchmark_ret_5 = benchmark_ret_20 = benchmark_trend_slope_20 = benchmark_realized_vol_20 = None
    relative_ret_20 = correlation_to_benchmark_20 = beta_to_benchmark_20 = None
    if benchmark_hist is not None and not benchmark_hist.empty:
        bench_close = benchmark_hist["Close"].astype(float).to_list()
        benchmark_ret_5 = _safe_log_return(bench_close, 5)
        benchmark_ret_20 = _safe_log_return(bench_close, 20)
        benchmark_trend_slope_20 = ind.log_slope(bench_close, 20)
        benchmark_realized_vol_20 = ind.realized_vol(bench_close, 20)
        relative_ret_20 = (ret_20 - benchmark_ret_20) if ret_20 is not None and benchmark_ret_20 is not None else None
        correlation_to_benchmark_20, beta_to_benchmark_20 = ind.correlation_beta(close, bench_close, 20)

    time_of_day_sin, time_of_day_cos, minute_of_session, day_of_week = _cyclical_time_features(hist.index[-1])
    if len(close) < 20:
        quality_flag = "INSUFFICIENT_HISTORY"
    else:
        quality_flag = "OK"

    return {
        "ret_1": _safe_log_return(close, 1),
        "ret_5": ret_5,
        "ret_20": ret_20,
        "ret_z_20": ind.zscore_latest(log_returns_arr, 20) if log_returns_arr.size else None,
        "range_pct_1": float((high[-1] - low[-1]) / close[-1]) if close[-1] else None,
        "close_to_high_pct": float((high[-1] - close[-1]) / (high[-1] - low[-1])) if high[-1] != low[-1] else 0.0,
        "close_to_low_pct": float((close[-1] - low[-1]) / (high[-1] - low[-1])) if high[-1] != low[-1] else 0.0,
        "sma_20_dist": _safe_distance(close, sma20),
        "ema_9_dist": _safe_distance(close, ema9),
        "trend_slope_20": ind.log_slope(close, 20),
        "rsi_14": float(rsi14[-1]) if len(rsi14) and not np.isnan(rsi14[-1]) else None,
        "consecutive_up_bars": ind.consecutive_up_bars(close),
        "volume_1": float(volume[-1]) if volume else None,
        "volume_z_20": ind.zscore_latest(volume, 20),
        "relative_volume_20": (float(volume[-1]) / (sum(volume[-20:]) / min(20, len(volume)))) if volume else None,
        "realized_vol_10": realized_vol_10,
        "realized_vol_20": realized_vol_20,
        "atr_pct_14": (float(atr14[-1]) / close[-1]) if len(atr14) and not np.isnan(atr14[-1]) and close[-1] else None,
        "vol_expansion_20_60": vol_expansion_20_60,
        "time_of_day_sin": time_of_day_sin,
        "time_of_day_cos": time_of_day_cos,
        "minute_of_session": minute_of_session,
        "day_of_week": day_of_week,
        "benchmark_ret_5": benchmark_ret_5,
        "benchmark_ret_20": benchmark_ret_20,
        "benchmark_trend_slope_20": benchmark_trend_slope_20,
        "benchmark_realized_vol_20": benchmark_realized_vol_20,
        "relative_ret_20": relative_ret_20,
        "correlation_to_benchmark_20": correlation_to_benchmark_20,
        "beta_to_benchmark_20": beta_to_benchmark_20,
        "__quality_flag": quality_flag,
    }


def build_intraday_rows(
    frame: pd.DataFrame,
    *,
    symbol: str,
    horizon_bars: int,
    benchmark_frame: pd.DataFrame | None = None,
    lookback_bars: int = 60,
) -> list[FeatureRow]:
    if frame.empty:
        return []

    ordered = frame.copy()
    ordered.index = pd.to_datetime(ordered.index, utc=True, errors="coerce")
    ordered = ordered[~ordered.index.isna()].sort_index()
    if benchmark_frame is not None and not benchmark_frame.empty:
        bench = benchmark_frame.copy()
        bench.index = pd.to_datetime(bench.index, utc=True, errors="coerce")
        bench = bench[~bench.index.isna()].sort_index()
    else:
        bench = None

    rows: list[FeatureRow] = []
    for idx in range(len(ordered)):
        if idx < lookback_bars:
            continue
        if idx + horizon_bars >= len(ordered):
            continue

        hist = ordered.iloc[: idx + 1]
        benchmark_hist = None
        if bench is not None and not bench.empty:
            bench_idx = bench.index.searchsorted(hist.index[-1], side="right") - 1
            if bench_idx >= 0:
                benchmark_hist = bench.iloc[: bench_idx + 1]
        feat = _build_feature_dict(hist, benchmark_hist)
        if feat["__quality_flag"] != "OK":
            continue
        entry_price = float(hist["Close"].iloc[-1])
        future_close = float(ordered["Close"].iloc[idx + horizon_bars])
        if entry_price <= 0 or future_close <= 0:
            continue
        target_return_pct = future_close / entry_price - 1.0
        target_return_bps = target_return_pct * 10000.0
        rows.append(
            FeatureRow(
                symbol=symbol,
                timestamp=_to_utc_timestamp(hist.index[-1]),
                entry_price=entry_price,
                target_return_pct=target_return_pct,
                target_return_bps=target_return_bps,
                features={k: v for k, v in feat.items() if k != "__quality_flag"},
                quality_flag="OK",
            )
        )
    return rows


def rows_to_frame(rows: Sequence[FeatureRow]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame()
    payload = []
    for row in rows:
        item = {
            "symbol": row.symbol,
            "timestamp": row.timestamp,
            "entry_price": row.entry_price,
            "target_return_pct": row.target_return_pct,
            "target_return_bps": row.target_return_bps,
            "feature_quality_flag": row.quality_flag,
        }
        item.update(row.features)
        payload.append(item)
    return pd.DataFrame(payload)


def resolve_date_buffer_days(interval: str, lookback_bars: int, horizon_bars: int) -> int:
    duration = pd.Timedelta(interval_duration(interval))
    total = (lookback_bars + horizon_bars + 20) * duration
    return max(5, int(ceil(total / pd.Timedelta(days=1))))
