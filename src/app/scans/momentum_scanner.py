from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import math
from typing import Callable, Iterable

import numpy as np
import pandas as pd

from app.config.models import AlpacaDataSource, DataCacheConfig
from app.data.loaders import build_alpaca_data_feed_with_cache
from app.db.models import SymbolUniverse
from app.scans.params import MomentumScanParams
from app.universes.providers import provider_for_universe


@dataclass(frozen=True)
class ExcludedSymbol:
    symbol: str
    reason: str


@dataclass(frozen=True)
class MomentumScanResult:
    symbol: str
    score: float
    features: dict[str, float | int | str | None]


@dataclass(frozen=True)
class MomentumScanOutput:
    results: list[MomentumScanResult]
    excluded: list[ExcludedSymbol]
    universe: str
    provider: str
    as_of: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_symbols(symbols: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in symbols:
        symbol = (item or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        ordered.append(symbol)
    return ordered


def _is_default_reject_symbol(symbol: str) -> bool:
    return ("." in symbol) or ("-" in symbol) or (len(symbol) > 5)


def resolve_universe_symbols(params: MomentumScanParams) -> tuple[list[str], str, list[ExcludedSymbol]]:
    excluded: list[ExcludedSymbol] = []

    explicit = _normalize_symbols(params.symbols)
    if explicit:
        return explicit[: params.max_symbols], "custom", excluded

    universe = SymbolUniverse(
        key="sp500",
        name="S&P 500",
        provider="wikipedia",
        provider_ref={"kind": "sp500"},
    )
    provider = provider_for_universe(universe)
    members = sorted(provider.fetch_membership(universe, as_of=date.today()))
    kept: list[str] = []
    for symbol in members:
        if _is_default_reject_symbol(symbol):
            excluded.append(ExcludedSymbol(symbol=symbol, reason="default_symbol_shape_reject"))
            continue
        kept.append(symbol)
        if len(kept) >= params.max_symbols:
            break
    return kept, "sp500", excluded


def _require_ohlcv(frame: pd.DataFrame, *, symbol: str) -> pd.DataFrame:
    missing = [col for col in ["Open", "High", "Low", "Close", "Volume"] if col not in frame.columns]
    if missing:
        raise RuntimeError(f"{symbol}: missing OHLCV columns {missing}")
    return frame[["Open", "High", "Low", "Close", "Volume"]].copy()


def _avg_dollar_volume_20d(frame: pd.DataFrame) -> float | None:
    if frame.empty:
        return None
    tail = frame.tail(20)
    if len(tail) < 20:
        return None
    value = (tail["Close"] * tail["Volume"]).mean()
    return float(value) if pd.notna(value) else None


def _rsi(series: pd.Series, period: int = 14) -> float | None:
    if len(series) < period + 1:
        return None
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = (-delta).clip(lower=0.0)
    roll_up = up.rolling(period).mean()
    roll_down = down.rolling(period).mean()
    last_up = roll_up.iloc[-1]
    last_down = roll_down.iloc[-1]
    if not pd.notna(last_up) or not pd.notna(last_down):
        return None
    if float(last_down) == 0.0:
        return 100.0
    rs = float(last_up) / float(last_down)
    return float(100.0 - (100.0 / (1.0 + rs)))


def _trend_slope_per_day(close: pd.Series) -> float | None:
    if len(close) < 5:
        return None
    y = np.log(close.astype(float).to_numpy())
    if not np.isfinite(y).all():
        return None
    x = np.arange(len(y), dtype=float)
    slope, _ = np.polyfit(x, y, 1)
    if not math.isfinite(float(slope)):
        return None
    return float(slope)


def compute_features(frame: pd.DataFrame, *, lookback_days: int) -> dict[str, float | int | str | None]:
    frame = _require_ohlcv(frame, symbol="(unknown)")
    frame = frame.sort_index()
    close = frame["Close"].astype(float)
    daily_returns = close.pct_change()

    def _ret(days: int) -> float | None:
        if len(close) < days + 1:
            return None
        start = close.iloc[-(days + 1)]
        end = close.iloc[-1]
        if not pd.notna(start) or not pd.notna(end) or float(start) == 0.0:
            return None
        return float(end / start - 1.0)

    ma50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else np.nan
    ma200 = close.rolling(200).mean().iloc[-1] if len(close) >= 200 else np.nan

    vol_20 = daily_returns.rolling(20).std().iloc[-1] if len(close) >= 21 else np.nan
    vol_60 = daily_returns.rolling(60).std().iloc[-1] if len(close) >= 61 else np.nan

    lookback = close.tail(lookback_days)
    slope = _trend_slope_per_day(lookback) if len(lookback) >= 5 else None

    rsi14 = _rsi(close, 14)

    ma50_val = float(ma50) if pd.notna(ma50) else None
    ma200_val = float(ma200) if pd.notna(ma200) else None
    ma_ratio = None
    if ma50_val is not None and ma200_val is not None and ma200_val != 0.0:
        ma_ratio = float(ma50_val / ma200_val)

    vol20_val = float(vol_20) if pd.notna(vol_20) else None
    vol60_val = float(vol_60) if pd.notna(vol_60) else None

    avg_dv_20 = _avg_dollar_volume_20d(frame)
    last_close = float(close.iloc[-1]) if not close.empty and pd.notna(close.iloc[-1]) else None

    return {
        "last_close": last_close,
        "avg_dollar_volume_20d": avg_dv_20,
        "ret_20d": _ret(20),
        "ret_60d": _ret(60),
        "ret_90d": _ret(90),
        "trend_slope_log_close_per_day": slope,
        "vol_20d": vol20_val,
        "vol_60d": vol60_val,
        "rsi_14": rsi14,
        "ma_50": ma50_val,
        "ma_200": ma200_val,
        "ma50_over_ma200": ma_ratio,
        "bars": int(len(frame)),
    }


def _zscore(values: dict[str, float | None]) -> dict[str, float]:
    data = np.array([v for v in values.values() if v is not None and math.isfinite(float(v))], dtype=float)
    if data.size == 0:
        return {k: 0.0 for k in values}
    mean = float(data.mean())
    std = float(data.std(ddof=0))
    if std == 0.0 or not math.isfinite(std):
        return {k: 0.0 for k in values}
    out: dict[str, float] = {}
    for k, v in values.items():
        if v is None or not math.isfinite(float(v)):
            out[k] = 0.0
        else:
            out[k] = float((float(v) - mean) / std)
    return out


def score_symbols(
    features_by_symbol: dict[str, dict[str, float | int | str | None]],
) -> dict[str, float]:
    ret20 = {s: (f.get("ret_20d") if isinstance(f.get("ret_20d"), (int, float)) else None) for s, f in features_by_symbol.items()}
    ret60 = {s: (f.get("ret_60d") if isinstance(f.get("ret_60d"), (int, float)) else None) for s, f in features_by_symbol.items()}
    ret90 = {s: (f.get("ret_90d") if isinstance(f.get("ret_90d"), (int, float)) else None) for s, f in features_by_symbol.items()}
    slope = {
        s: (f.get("trend_slope_log_close_per_day") if isinstance(f.get("trend_slope_log_close_per_day"), (int, float)) else None)
        for s, f in features_by_symbol.items()
    }
    vol20 = {s: (f.get("vol_20d") if isinstance(f.get("vol_20d"), (int, float)) else None) for s, f in features_by_symbol.items()}

    z_ret20 = _zscore(ret20)
    z_ret60 = _zscore(ret60)
    z_ret90 = _zscore(ret90)
    z_slope = _zscore(slope)
    z_vol20 = _zscore(vol20)

    scores: dict[str, float] = {}
    for symbol in features_by_symbol:
        base = 0.35 * z_ret20[symbol] + 0.30 * z_ret60[symbol] + 0.20 * z_ret90[symbol] + 0.15 * z_slope[symbol]
        penalty = 0.25 * z_vol20[symbol]
        scores[symbol] = float(base - penalty)
    return scores


def _alpaca_fetcher(
    *,
    cache_config: DataCacheConfig | None = None,
    force_refresh: bool = False,
) -> Callable[[str, int], pd.DataFrame]:
    def _fetch(symbol: str, days: int) -> pd.DataFrame:
        end_date = date.today()
        start_date = end_date - timedelta(days=max(5, days + 5))
        source = AlpacaDataSource(type="alpaca", symbol=symbol, interval="1d", feed="iex")  # type: ignore[arg-type]
        frame, _ = build_alpaca_data_feed_with_cache(
            source,
            start_date,
            end_date,
            cache_config=cache_config,
            force_refresh=force_refresh,
        )
        return frame

    return _fetch


def run_momentum_scan(
    params: MomentumScanParams,
    *,
    as_of: datetime | None = None,
    fetch_short: Callable[[str, int], pd.DataFrame] | None = None,
    fetch_full: Callable[[str, int], pd.DataFrame] | None = None,
) -> MomentumScanOutput:
    as_of = as_of or _utc_now()
    fetch_short = fetch_short or _alpaca_fetcher()
    fetch_full = fetch_full or _alpaca_fetcher()

    symbols, universe, excluded = resolve_universe_symbols(params)

    survivors: list[str] = []
    for symbol in symbols:
        try:
            short_frame = fetch_short(symbol, 25)
            short_frame = _require_ohlcv(short_frame, symbol=symbol)
            avg_dv_20 = _avg_dollar_volume_20d(short_frame)
            if avg_dv_20 is None:
                excluded.append(ExcludedSymbol(symbol=symbol, reason="insufficient_bars_for_prefilter"))
                continue
            last_close = short_frame["Close"].iloc[-1]
            if not pd.notna(last_close):
                excluded.append(ExcludedSymbol(symbol=symbol, reason="missing_last_close"))
                continue
            last_close_val = float(last_close)
            if last_close_val < float(params.min_price):
                excluded.append(ExcludedSymbol(symbol=symbol, reason="below_min_price"))
                continue
            if avg_dv_20 < float(params.min_avg_dollar_volume):
                excluded.append(ExcludedSymbol(symbol=symbol, reason="low_avg_dollar_volume_20d"))
                continue
            survivors.append(symbol)
        except Exception as exc:
            excluded.append(ExcludedSymbol(symbol=symbol, reason=f"prefilter_error:{type(exc).__name__}"))

    features_by_symbol: dict[str, dict[str, float | int | str | None]] = {}
    for symbol in survivors:
        try:
            # Fetch enough buffer to compute MA200 and requested lookback slope.
            days = int(params.lookback_days) + 220
            full_frame = fetch_full(symbol, days)
            full_frame = _require_ohlcv(full_frame, symbol=symbol)
            feats = compute_features(full_frame, lookback_days=int(params.lookback_days))
            # Enforce the liquidity/price filters again on full frame (guard against short-window artifacts).
            avg_dv = feats.get("avg_dollar_volume_20d")
            last_close = feats.get("last_close")
            if not isinstance(last_close, (int, float)) or last_close < float(params.min_price):
                excluded.append(ExcludedSymbol(symbol=symbol, reason="below_min_price_full"))
                continue
            if not isinstance(avg_dv, (int, float)) or avg_dv < float(params.min_avg_dollar_volume):
                excluded.append(ExcludedSymbol(symbol=symbol, reason="low_avg_dollar_volume_20d_full"))
                continue
            features_by_symbol[symbol] = feats
        except Exception as exc:
            excluded.append(ExcludedSymbol(symbol=symbol, reason=f"full_fetch_or_compute_error:{type(exc).__name__}"))

    scores = score_symbols(features_by_symbol)
    ordered = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

    results: list[MomentumScanResult] = []
    for symbol, score in ordered:
        results.append(MomentumScanResult(symbol=symbol, score=float(score), features=features_by_symbol[symbol]))

    return MomentumScanOutput(
        results=results,
        excluded=excluded,
        universe=universe,
        provider="alpaca",
        as_of=as_of,
    )
