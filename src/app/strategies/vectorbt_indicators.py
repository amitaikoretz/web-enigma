from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import vectorbt as vbt


US_EASTERN = ZoneInfo("America/New_York")


def _apply_columnwise(arr: np.ndarray, fn: Any) -> np.ndarray:
    array = np.asarray(arr, dtype=float)
    if array.ndim == 1:
        return fn(array)
    if array.ndim != 2:
        raise ValueError("Indicator inputs must be 1D or 2D")
    columns = [fn(array[:, idx]) for idx in range(array.shape[1])]
    return np.column_stack(columns)


def _sma_apply(close: np.ndarray, window: int) -> np.ndarray:
    def _run(arr: np.ndarray) -> np.ndarray:
        out = np.full(arr.shape, np.nan, dtype=float)
        if window <= 0 or arr.size < window:
            return out
        csum = np.cumsum(arr, dtype=float)
        csum[window:] = csum[window:] - csum[:-window]
        out[window - 1 :] = csum[window - 1 :] / window
        return out

    arr = np.asarray(close, dtype=float)
    return _apply_columnwise(arr, _run)


def _ema_apply(close: np.ndarray, window: int) -> np.ndarray:
    def _run(arr: np.ndarray) -> np.ndarray:
        out = np.full(arr.shape, np.nan, dtype=float)
        valid_indices = np.flatnonzero(~np.isnan(arr))
        if window <= 0 or valid_indices.size < window:
            return out
        alpha = 2.0 / (window + 1.0)
        seed_indices = valid_indices[:window]
        seed_end = int(seed_indices[-1])
        out[seed_end] = float(np.mean(arr[seed_indices]))
        prev = out[seed_end]
        for i in valid_indices[window:]:
            prev = alpha * arr[i] + (1.0 - alpha) * prev
            out[i] = prev
        return out

    arr = np.asarray(close, dtype=float)
    return _apply_columnwise(arr, _run)


def _atr_apply(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    def _run(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
        out = np.full(c.shape, np.nan, dtype=float)
        if window <= 0 or c.size < window:
            return out
        tr = np.empty_like(c)
        tr[0] = h[0] - l[0]
        prev_close = c[:-1]
        tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - prev_close), np.abs(l[1:] - prev_close)])
        out[window - 1] = np.mean(tr[:window])
        for i in range(window, c.size):
            out[i] = (out[i - 1] * (window - 1) + tr[i]) / window
        return out

    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    if c.ndim == 1:
        return _run(h, l, c)
    if c.ndim != 2:
        raise ValueError("Indicator inputs must be 1D or 2D")
    columns = [_run(h[:, idx], l[:, idx], c[:, idx]) for idx in range(c.shape[1])]
    return np.column_stack(columns)


def _close_strength_apply(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    def _run(h: np.ndarray, l: np.ndarray, c: np.ndarray) -> np.ndarray:
        bar_ranges = h - l
        return np.where(bar_ranges <= 0.0, 1.0, (c - l) / bar_ranges)

    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    if c.ndim == 1:
        return _run(h, l, c)
    if c.ndim != 2:
        raise ValueError("Indicator inputs must be 1D or 2D")
    columns = [_run(h[:, idx], l[:, idx], c[:, idx]) for idx in range(c.shape[1])]
    return np.column_stack(columns)


def _session_vwap_apply(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    volume: np.ndarray,
    session_id: np.ndarray,
) -> np.ndarray:
    def _run(h: np.ndarray, l: np.ndarray, c: np.ndarray, v: np.ndarray, sid: np.ndarray) -> np.ndarray:
        out = np.full(c.shape, np.nan, dtype=float)
        cumulative_volume = 0.0
        cumulative_turnover = 0.0
        prev_session: Any = None
        for idx in range(len(c)):
            if prev_session is None or sid[idx] != prev_session:
                cumulative_volume = 0.0
                cumulative_turnover = 0.0
                prev_session = sid[idx]
            typical_price = (h[idx] + l[idx] + c[idx]) / 3.0
            cumulative_volume += float(v[idx])
            cumulative_turnover += float(typical_price * v[idx])
            if cumulative_volume != 0.0:
                out[idx] = cumulative_turnover / cumulative_volume
        return out

    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    v = np.asarray(volume, dtype=float)
    sid = np.asarray(session_id)
    if c.ndim == 1:
        return _run(h, l, c, v, sid)
    if c.ndim != 2:
        raise ValueError("Indicator inputs must be 1D or 2D")
    columns = [_run(h[:, idx], l[:, idx], c[:, idx], v[:, idx], sid[:, idx] if sid.ndim == 2 else sid) for idx in range(c.shape[1])]
    return np.column_stack(columns)


SMAIndicator = vbt.IndicatorFactory(
    class_name="SMAIndicator",
    short_name="sma",
    input_names=["close"],
    param_names=["window"],
    output_names=["ma"],
).from_apply_func(_sma_apply)

EMAIndicator = vbt.IndicatorFactory(
    class_name="EMAIndicator",
    short_name="ema",
    input_names=["close"],
    param_names=["window"],
    output_names=["ma"],
).from_apply_func(_ema_apply)

ATRIndicator = vbt.IndicatorFactory(
    class_name="ATRIndicator",
    short_name="atr",
    input_names=["high", "low", "close"],
    param_names=["window"],
    output_names=["atr"],
).from_apply_func(_atr_apply)

CloseStrengthIndicator = vbt.IndicatorFactory(
    class_name="CloseStrengthIndicator",
    short_name="close_strength",
    input_names=["high", "low", "close"],
    output_names=["strength"],
).from_apply_func(_close_strength_apply)

SessionVWAPIndicator = vbt.IndicatorFactory(
    class_name="SessionVWAPIndicator",
    short_name="session_vwap",
    input_names=["high", "low", "close", "volume", "session_id"],
    output_names=["vwap"],
).from_apply_func(_session_vwap_apply)


def session_ids_from_index(index: pd.Index) -> np.ndarray:
    """Return stable numeric session identifiers for a DatetimeIndex."""
    if not isinstance(index, pd.DatetimeIndex):
        raise ValueError("Session IDs require a DatetimeIndex")
    session_ids: list[int] = []
    prev_date: datetime | None = None
    current_session = -1
    for timestamp in index:
        date = timestamp.date()
        if prev_date is None or date != prev_date:
            current_session += 1
            prev_date = date
        session_ids.append(current_session)
    return np.asarray(session_ids, dtype=int)


def run_sma(close: pd.Series | pd.DataFrame, window: Any, *, param_product: bool = False):
    return SMAIndicator.run(close, window=window, param_product=param_product).ma


def run_ema(close: pd.Series | pd.DataFrame, window: Any, *, param_product: bool = False):
    return EMAIndicator.run(close, window=window, param_product=param_product).ma


def run_atr(
    high: pd.Series | pd.DataFrame,
    low: pd.Series | pd.DataFrame,
    close: pd.Series | pd.DataFrame,
    window: Any,
    *,
    param_product: bool = False,
):
    return ATRIndicator.run(high, low, close, window=window, param_product=param_product).atr


def run_close_strength(high: pd.Series | pd.DataFrame, low: pd.Series | pd.DataFrame, close: pd.Series | pd.DataFrame):
    return CloseStrengthIndicator.run(high, low, close).strength


def run_session_vwap(
    high: pd.Series | pd.DataFrame,
    low: pd.Series | pd.DataFrame,
    close: pd.Series | pd.DataFrame,
    volume: pd.Series | pd.DataFrame,
    index: pd.Index,
):
    session_id = session_ids_from_index(index)
    return SessionVWAPIndicator.run(high, low, close, volume, session_id=session_id).vwap
