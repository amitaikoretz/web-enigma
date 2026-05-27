from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def sma(values: Sequence[float], period: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    out = np.full(arr.shape, np.nan, dtype=float)
    if period <= 0 or arr.size < period:
        return out
    csum = np.cumsum(arr, dtype=float)
    csum[period:] = csum[period:] - csum[:-period]
    out[period - 1 :] = csum[period - 1 :] / period
    return out


def rsi(values: Sequence[float], period: int) -> np.ndarray:
    close = np.asarray(values, dtype=float)
    out = np.full(close.shape, np.nan, dtype=float)
    if period <= 0 or close.size <= period:
        return out
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.empty_like(close)
    avg_loss = np.empty_like(close)
    avg_gain[:] = np.nan
    avg_loss[:] = np.nan

    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])

    for i in range(period + 1, close.size):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

    rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.nan), where=avg_loss != 0)
    out = 100.0 - (100.0 / (1.0 + rs))
    out[np.isnan(avg_loss)] = np.nan
    out[(avg_loss == 0) & (~np.isnan(avg_gain))] = 100.0
    return out


def atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int) -> np.ndarray:
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    out = np.full(c.shape, np.nan, dtype=float)
    if period <= 0 or c.size < period:
        return out
    tr = np.empty_like(c)
    tr[0] = h[0] - l[0]
    prev_close = c[:-1]
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - prev_close), np.abs(l[1:] - prev_close)])
    out[period - 1] = np.mean(tr[:period])
    for i in range(period, c.size):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out


def log_slope(values: Sequence[float], period: int) -> float | None:
    arr = np.asarray(values[-period:], dtype=float)
    if arr.size < period or np.any(arr <= 0) or np.any(np.isnan(arr)):
        return None
    y = np.log(arr)
    x = np.arange(period, dtype=float)
    if np.allclose(x.std(), 0):
        return None
    slope = np.polyfit(x, y, 1)[0]
    return float(slope)


def zscore_latest(values: Sequence[float], window: int) -> float | None:
    arr = np.asarray(values[-window:], dtype=float)
    if arr.size < window:
        return None
    mean = float(np.mean(arr))
    std = float(np.std(arr))
    if std == 0:
        return 0.0
    return float((arr[-1] - mean) / std)


def percentile_rank_latest(values: Sequence[float], window: int) -> float | None:
    arr = np.asarray(values[-window:], dtype=float)
    if arr.size < window:
        return None
    latest = arr[-1]
    return float(np.mean(arr <= latest))


def realized_vol(close: Sequence[float], window: int) -> float | None:
    arr = np.asarray(close[-window - 1 :], dtype=float)
    if arr.size < window + 1 or np.any(arr <= 0):
        return None
    log_returns = np.diff(np.log(arr))
    if log_returns.size < window:
        return None
    return float(np.std(log_returns[-window:]))


def consecutive_up_bars(close: Sequence[float]) -> int:
    arr = np.asarray(close, dtype=float)
    count = 0
    for i in range(len(arr) - 1, 0, -1):
        if arr[i] > arr[i - 1]:
            count += 1
        else:
            break
    return count


def correlation_beta(
    symbol_close: Sequence[float],
    index_close: Sequence[float],
    window: int,
) -> tuple[float | None, float | None]:
    sym = np.asarray(symbol_close[-window - 1 :], dtype=float)
    idx = np.asarray(index_close[-window - 1 :], dtype=float)
    if sym.size < window + 1 or idx.size < window + 1:
        return None, None
    sym_ret = np.diff(np.log(sym))
    idx_ret = np.diff(np.log(idx))
    if sym_ret.size < window or idx_ret.size < window:
        return None, None
    sym_ret = sym_ret[-window:]
    idx_ret = idx_ret[-window:]
    if np.std(sym_ret) == 0 or np.std(idx_ret) == 0:
        return None, None
    corr = float(np.corrcoef(sym_ret, idx_ret)[0, 1])
    var_idx = float(np.var(idx_ret))
    beta = float(np.cov(sym_ret, idx_ret)[0, 1] / var_idx) if var_idx else None
    return corr, beta
