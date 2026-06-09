"""Trigger definitions, parameter models, and registry metadata for strategy entry rules."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Callable
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.strategies.components import TriggerCore
from app.strategies.candidates import EntryIntent
from app.strategies.core import StrategyContext, StrategyDecision
from app.strategies.entry_plans import atr_entry_intent, fixed_pct_entry_intent
from app.strategies.implementations import (
    _adx,
    _atr,
    _benchmark_regime_ok,
    _bars_held,
    _close_strength,
    _closes,
    _ema,
    _highs,
    _in_session_window,
    _is_last_bar_of_session,
    _is_new_session,
    _lows,
    _macd,
    _minutes_since_rth_open,
    _rsi,
    _session_vwap,
    _sma,
    _resample_session_bars,
    _volume_rally_entry_signal,
    _volumes,
)
from app.strategies.regime import RegimeClassifier, regime_params_from_strategy, resolve_regime_warmup_bars
from app.strategies.vectorbt_support import VectorbtBuildContext, VectorbtSpec


US_EASTERN = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


class TriggerSelection(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_trigger(self) -> "TriggerSelection":
        if self.name not in TRIGGER_REGISTRY:
            available = ", ".join(sorted(TRIGGER_REGISTRY.keys()))
            raise ValueError(f"Unknown trigger '{self.name}'. Available: {available}")
        self.params = validate_trigger_params(self.name, self.params)
        return self

    def stable_id(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:10]  # noqa: S324


class SmaCrossTriggerParams(BaseModel):
    fast: int = Field(default=8, ge=2, description="Fast SMA lookback window in bars.")
    slow: int = Field(default=21, ge=3, description="Slow SMA lookback window in bars.")
    stake: float = Field(default=1.0, gt=0, description="Order size in shares/contracts to buy on a cross-up.")

    @model_validator(mode="after")
    def _validate_windows(self) -> "SmaCrossTriggerParams":
        if self.fast >= self.slow:
            raise ValueError("fast must be smaller than slow")
        return self


class RsiReversionTriggerParams(BaseModel):
    period: int = Field(default=14, ge=2, description="RSI lookback window in bars.")
    oversold: float = Field(default=30.0, ge=1, le=60, description="RSI threshold that triggers a long entry.")
    stake: float = Field(default=1.0, gt=0, description="Order size in shares/contracts to buy when oversold.")


class BuyAndHoldTriggerParams(BaseModel):
    stake: float = Field(default=1.0, gt=0, description="Initial order size placed on the first bar.")


class BreakoutChannelTriggerParams(BaseModel):
    lookback: int = Field(default=20, ge=2, description="Number of prior bars used to define the breakout channel.")
    stake: float = Field(default=1.0, gt=0, description="Order size in shares/contracts on breakout.")
    stop_loss_pct: float = Field(default=0.01, gt=0, lt=0.5, description="Fixed stop-loss distance as a fraction of entry price.")
    take_profit_pct: float = Field(default=0.02, gt=0, lt=1.0, description="Fixed take-profit distance as a fraction of entry price.")
    max_hold_bars: int = Field(default=20, ge=1, description="Maximum bars to hold the position before forcing an exit.")


class BuyOcoAtrTriggerParams(BaseModel):
    stake: float = Field(default=1.0, gt=0, description="Order size in shares/contracts to buy on cross-up.")
    atr_period: int = Field(default=14, ge=2, description="ATR lookback used to estimate volatility for exit intent.")
    entry_sma: int = Field(default=20, ge=2, description="SMA lookback used to detect the cross-up entry signal.")
    sl_atr_mult: float = Field(default=1.5, gt=0, description="Stop-loss distance measured in ATR multiples.")
    tp_atr_mult: float = Field(default=3.0, gt=0, description="Take-profit distance measured in ATR multiples.")
    max_hold_bars: int = Field(default=24, ge=1, description="Maximum bars to hold before the attached intent expires.")


class VwapPullbackTriggerParams(BaseModel):
    stake: float = Field(default=1.0, gt=0, description="Order size in shares/contracts to buy on confirmation.")
    benchmark_symbol: str = Field(min_length=1, description="Benchmark symbol used to confirm the broader trend.")
    benchmark_resolution_minutes: int = Field(
        default=15,
        ge=1,
        description="Benchmark resample resolution in minutes used for the regime filter.",
    )
    trend_ema_fast: int = Field(default=9, ge=2, description="Fast EMA lookback for the traded symbol trend filter.")
    trend_ema_mid: int = Field(default=20, ge=3, description="Middle EMA lookback for the traded symbol trend filter.")
    trend_ema_slow: int = Field(default=50, ge=4, description="Slow EMA lookback for the traded symbol trend filter.")
    benchmark_ema_fast: int = Field(default=20, ge=2, description="Fast EMA lookback for the benchmark trend filter.")
    benchmark_ema_slow: int = Field(default=50, ge=3, description="Slow EMA lookback for the benchmark trend filter.")
    volume_window: int = Field(default=20, ge=2, description="Bars used to compute the average volume baseline.")
    volume_spike_mult: float = Field(default=1.2, gt=0.0, description="Minimum multiple of average volume required for entry.")
    pullback_distance_pct: float = Field(default=0.003, gt=0.0, lt=0.1, description="Allowed pullback distance from the trend before entry.")
    min_closes_above_vwap: int = Field(default=2, ge=1, le=3, description="Minimum recent closes that must remain above VWAP.")
    recent_close_window: int = Field(default=3, ge=3, le=5, description="Number of recent closes considered for the VWAP confirmation.")
    max_entry_gap_pct: float = Field(default=0.0025, gt=0.0, lt=0.1, description="Maximum gap between the signal bar and the entry price.")
    stop_buffer_pct: float = Field(default=0.0015, gt=0.0, lt=0.1, description="Extra stop buffer below the pullback/reference level.")
    max_stop_distance_pct: float = Field(default=0.0075, gt=0.0, lt=0.1, description="Hard cap on stop distance as a fraction of entry.")
    max_stop_atr_mult: float = Field(default=1.5, gt=0.0, description="Hard cap on stop distance measured in ATR multiples.")
    session_morning_start_minutes: int = Field(default=15, ge=0, description="Minutes after the session open when morning entries may begin.")
    session_morning_end_minutes: int = Field(default=105, ge=0, description="Minutes after the session open when morning entries stop.")
    session_afternoon_start_minutes: int = Field(default=240, ge=0, description="Minutes after the session open when afternoon entries may begin.")
    session_afternoon_end_minutes: int = Field(default=345, ge=0, description="Minutes after the session open when afternoon entries stop.")

    @model_validator(mode="after")
    def _validate_windows(self) -> "VwapPullbackTriggerParams":
        if self.trend_ema_fast >= self.trend_ema_mid or self.trend_ema_mid >= self.trend_ema_slow:
            raise ValueError("trend EMA values must satisfy fast < mid < slow")
        if self.benchmark_ema_fast >= self.benchmark_ema_slow:
            raise ValueError("benchmark_ema_fast must be smaller than benchmark_ema_slow")
        if self.min_closes_above_vwap > self.recent_close_window:
            raise ValueError("min_closes_above_vwap must be <= recent_close_window")
        if self.session_morning_start_minutes >= self.session_morning_end_minutes:
            raise ValueError("morning session window must have start < end")
        if self.session_afternoon_start_minutes >= self.session_afternoon_end_minutes:
            raise ValueError("afternoon session window must have start < end")
        return self


class VolumeRallyTriggerParams(BaseModel):
    stake: float = Field(default=1.0, gt=0, description="Order size in shares/contracts on confirmed breakout.")
    volume_window: int = Field(default=20, ge=2, description="Bars used to compute the average volume baseline.")
    volume_spike_mult: float = Field(default=3.0, gt=0, description="Minimum volume multiple required to treat a bar as a spike.")
    breakout_lookback: int = Field(default=20, ge=2, description="Lookback window used to detect the breakout high.")
    atr_period: int = Field(default=14, ge=2, description="ATR lookback used for volatility and exit intent.")
    atr_expansion_mult: float = Field(default=0.5, gt=0, description="Minimum ATR expansion threshold used in the confirmation signal.")
    macd_fast: int = Field(default=12, ge=2, description="Fast MACD EMA lookback.")
    macd_slow: int = Field(default=26, ge=3, description="Slow MACD EMA lookback.")
    macd_signal: int = Field(default=9, ge=2, description="MACD signal-line EMA lookback.")
    adx_period: int = Field(default=14, ge=2, description="ADX lookback used to confirm trend strength.")
    adx_min: float = Field(default=25.0, ge=0.0, description="Minimum ADX value required for entry confirmation.")
    sl_atr_mult: float = Field(default=1.5, gt=0, description="Stop-loss distance measured in ATR multiples.")
    tp_atr_mult: float = Field(default=3.0, gt=0, description="Take-profit distance measured in ATR multiples.")
    max_hold_bars: int = Field(default=48, ge=1, description="Maximum bars to hold before the exit intent times out.")
    stale_bars: int = Field(default=0, ge=0, description="Bars without progress before the trade is considered stale.")
    cooldown_bars: int = Field(default=0, ge=0, description="Bars to wait after an exit before the next entry.")
    session_start_minutes: int = Field(default=0, ge=0, description="Minutes after session open when entries may begin.")
    session_end_minutes: int = Field(default=0, ge=0, description="Minutes after session open when entries stop.")
    min_close_strength: float = Field(default=0.0, ge=0.0, le=1.0, description="Minimum close-strength ratio required for a valid breakout bar.")
    max_trades_per_session: int = Field(default=0, ge=0, description="Maximum trades allowed per session; zero disables the cap.")
    min_confirmations: int = Field(default=3, ge=2, le=6, description="Minimum number of confirmation checks that must pass.")
    regime_enabled: bool = False
    volatility_regime_window: int = Field(default=0, ge=0, description="Volatility regime lookback used to activate regime gating.")
    volatility_regime_max_mult: float = Field(default=2.0, gt=0, description="Upper bound on allowed volatility regime expansion.")
    volatility_regime_min_mult: float = Field(default=0.5, gt=0, description="Lower bound on allowed volatility regime contraction.")
    regime_adx_min: float = Field(default=25.0, ge=0.0, description="Minimum ADX required for the current regime to remain tradeable.")
    regime_slope_lookback: int = Field(default=20, ge=2, description="Lookback used to estimate the regime slope.")
    regime_slope_min: float = Field(default=0.0, description="Minimum slope required for regime tradeability.")
    benchmark_symbol: str = Field(default="", description="Optional benchmark symbol used for market-filter confirmation.")
    benchmark_sma_period: int = Field(default=20, ge=2, description="Benchmark SMA lookback used for trend confirmation.")
    benchmark_adx_period: int = Field(default=14, ge=2, description="Benchmark ADX lookback used for trend confirmation.")
    benchmark_adx_min: float = Field(default=25.0, ge=0.0, description="Minimum benchmark ADX required for the filter to pass.")
    benchmark_require_above_sma: bool = Field(default=True, description="Require the benchmark to close above its SMA before entry.")

    @model_validator(mode="after")
    def _validate_params(self) -> "VolumeRallyTriggerParams":
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast must be smaller than macd_slow")
        if self.volatility_regime_window > 0:
            self.regime_enabled = True
        if self.benchmark_symbol.strip() and not self.benchmark_require_above_sma and self.benchmark_adx_min <= 0:
            raise ValueError("benchmark filter requires benchmark_require_above_sma or benchmark_adx_min > 0")
        return self


class FastUpswingTriggerParams(BaseModel):
    stake: float = Field(default=1.0, gt=0, description="Order size in shares/contracts on confirmation.")
    return_lookback: int = Field(default=5, ge=2, description="Bars used to measure the recent return burst.")
    volatility_window: int = Field(default=20, ge=2, description="Bars used to estimate recent realized volatility.")
    min_return_burst_sigma: float = Field(default=1.0, gt=0.0, description="Minimum return burst measured in volatility units.")
    volume_window: int = Field(default=20, ge=2, description="Bars used to compute the average volume baseline.")
    min_relative_volume: float = Field(default=1.5, gt=0.0, description="Minimum relative volume compared with the baseline.")
    min_volume_zscore: float = Field(default=1.0, gt=0.0, description="Minimum z-score of the current bar's volume.")
    min_consecutive_up_bars: int = Field(default=3, ge=2, description="Minimum number of consecutive up bars required.")
    min_close_strength: float = Field(default=0.65, ge=0.0, le=1.0, description="Minimum close-strength ratio for the current bar.")
    require_vwap: bool = Field(default=True, description="Require the current close to remain above VWAP.")
    breakout_lookback: int = Field(default=5, ge=2, description="Lookback used to confirm a short breakout condition.")
    require_breakout: bool = Field(default=False, description="Require the price to break above the prior lookback high.")
    atr_period: int = Field(default=14, ge=2, description="ATR lookback used for stop and target intent.")
    sl_atr_mult: float = Field(default=1.5, gt=0, description="Stop-loss distance measured in ATR multiples.")
    tp_atr_mult: float = Field(default=3.0, gt=0, description="Take-profit distance measured in ATR multiples.")
    max_hold_bars: int = Field(default=24, ge=1, description="Maximum bars to hold before the exit intent times out.")
    adx_period: int = Field(default=14, ge=2, description="ADX lookback used when trend-strength gating is enabled.")
    adx_min: float = Field(default=0.0, ge=0.0, description="Minimum ADX value required when ADX gating is enabled.")


class SmaCrossTrigger(TriggerCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        if len(closes) < 2:
            return StrategyDecision.hold("need_more_bars")
        fast = _sma(closes, int(self.params["fast"]))
        slow = _sma(closes, int(self.params["slow"]))
        if np.isnan(fast[-1]) or np.isnan(slow[-1]) or np.isnan(fast[-2]) or np.isnan(slow[-2]):
            return StrategyDecision.hold("warmup")
        cross_up = fast[-1] > slow[-1] and fast[-2] <= slow[-2]
        if cross_up:
            return StrategyDecision.buy(float(self.params["stake"]), "cross_up")
        return StrategyDecision.hold()


class RsiReversionTrigger(TriggerCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        rsi = _rsi(closes, int(self.params["period"]))
        if np.isnan(rsi[-1]):
            return StrategyDecision.hold("warmup")
        if float(rsi[-1]) <= float(self.params["oversold"]):
            return StrategyDecision.buy(float(self.params["stake"]), "oversold")
        return StrategyDecision.hold()


class BuyAndHoldTrigger(TriggerCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self.has_entered = False

    def vectorbt_supported(self) -> bool:
        return True

    def load_state(self, state: dict[str, Any] | None) -> None:
        self.has_entered = bool((state or {}).get("has_entered", False))

    def dump_state(self) -> dict[str, Any]:
        return {"has_entered": self.has_entered}

    def vectorbt_spec(self, context: VectorbtBuildContext) -> VectorbtSpec | None:
        entries = np.zeros(len(context.index), dtype=bool)
        if len(entries) > 0:
            entries[0] = True
        return VectorbtSpec(entries=entries, size=float(self.params["stake"]), warmup_bars=1)

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        if self.has_entered:
            return StrategyDecision.hold()
        self.has_entered = True
        return StrategyDecision.buy(float(self.params["stake"]), "initial_entry")


class BreakoutChannelTrigger(TriggerCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        lookback = int(self.params["lookback"])
        if len(context.bars) <= lookback:
            return StrategyDecision.hold("warmup")
        lookback_bars = context.bars[-(lookback + 1) : -1]
        prev_highest = max(bar.high for bar in lookback_bars)
        if context.bar.close > prev_highest:
            entry_intent = fixed_pct_entry_intent(
                context,
                self.params,
                signal_score=1.0,
                signal_reason="breakout",
            )
            return StrategyDecision.buy(float(self.params["stake"]), "breakout", entry_intent=entry_intent)
        return StrategyDecision.hold()


class BuyOcoAtrTrigger(TriggerCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        if len(closes) < 2:
            return StrategyDecision.hold("need_more_bars")
        atr = _atr(_highs(context.bars), _lows(context.bars), closes, int(self.params["atr_period"]))
        sma = _sma(closes, int(self.params["entry_sma"]))
        if np.isnan(sma[-1]) or np.isnan(sma[-2]) or np.isnan(atr[-1]):
            return StrategyDecision.hold("warmup")
        cross_up = closes[-1] > sma[-1] and closes[-2] <= sma[-2]
        if cross_up:
            entry_intent = atr_entry_intent(
                float(context.bar.close),
                float(atr[-1]),
                sl_mult=float(self.params["sl_atr_mult"]),
                tp_mult=float(self.params["tp_atr_mult"]),
                horizon_bars=int(self.params["max_hold_bars"]),
                signal_score=1.0,
                signal_reason="cross_up",
            )
            return StrategyDecision.buy(float(self.params["stake"]), "cross_up", entry_intent=entry_intent)
        return StrategyDecision.hold()


def _bars_in_allowed_session_window(
    bar: Any,
    *,
    morning_start: int,
    morning_end: int,
    afternoon_start: int,
    afternoon_end: int,
) -> bool:
    # Split the trading day into two allowed windows so intraday triggers can avoid
    # the open/close while still allowing a second entry window later in the session.
    minutes_since_open = _minutes_since_rth_open(bar)
    if minutes_since_open is None:
        return False
    return (morning_start <= minutes_since_open <= morning_end) or (
        afternoon_start <= minutes_since_open <= afternoon_end
    )


def _timestamp_to_eastern(timestamp: datetime | Any) -> datetime:
    if hasattr(timestamp, "to_pydatetime"):
        timestamp = timestamp.to_pydatetime()
    if not isinstance(timestamp, datetime):
        raise TypeError(f"Expected datetime, got {type(timestamp)!r}")
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))
    return timestamp.astimezone(US_EASTERN)


def _minutes_since_rth_open_timestamp(timestamp: datetime | Any) -> int | None:
    eastern = _timestamp_to_eastern(timestamp)
    session_open = datetime.combine(eastern.date(), RTH_OPEN, tzinfo=US_EASTERN)
    session_close = datetime.combine(eastern.date(), RTH_CLOSE, tzinfo=US_EASTERN)
    if eastern < session_open or eastern >= session_close:
        return None
    return int((eastern - session_open).total_seconds() // 60)


def _timestamp_in_allowed_session_window(
    timestamp: datetime | Any,
    *,
    morning_start: int,
    morning_end: int,
    afternoon_start: int,
    afternoon_end: int,
) -> bool:
    if morning_start <= 0 and morning_end <= 0 and afternoon_start <= 0 and afternoon_end <= 0:
        return True
    minutes_since_open = _minutes_since_rth_open_timestamp(timestamp)
    if minutes_since_open is None:
        return False
    return (morning_start <= minutes_since_open <= morning_end) or (
        afternoon_start <= minutes_since_open <= afternoon_end
    )


def _frame_session_vwap(frame: pd.DataFrame) -> np.ndarray:
    typical_price = ((frame["High"].astype(float) + frame["Low"].astype(float) + frame["Close"].astype(float)) / 3.0).to_numpy()
    volumes = frame["Volume"].astype(float).to_numpy()
    out = np.full(len(frame), np.nan, dtype=float)
    cumulative_volume = 0.0
    cumulative_turnover = 0.0
    session_date: date | None = None
    for idx, timestamp in enumerate(frame.index):
        bar_date = timestamp.date() if hasattr(timestamp, "date") else date.fromisoformat(str(timestamp)[:10])
        if session_date is not None and bar_date != session_date:
            cumulative_volume = 0.0
            cumulative_turnover = 0.0
        session_date = bar_date
        cumulative_volume += float(volumes[idx])
        cumulative_turnover += float(typical_price[idx] * volumes[idx])
        if cumulative_volume != 0:
            out[idx] = cumulative_turnover / cumulative_volume
    return out


def _frame_close_strength(frame: pd.DataFrame) -> np.ndarray:
    highs = frame["High"].astype(float).to_numpy()
    lows = frame["Low"].astype(float).to_numpy()
    closes = frame["Close"].astype(float).to_numpy()
    bar_ranges = highs - lows
    return np.where(bar_ranges <= 0.0, 1.0, (closes - lows) / bar_ranges)


def _resample_session_frame(frame: pd.DataFrame, interval_minutes: int) -> pd.DataFrame:
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")
    if frame.empty:
        return frame.iloc[0:0].copy()
    required = {"Open", "High", "Low", "Close", "Volume"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise ValueError(f"Data frame is missing columns: {missing}")
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("Data frame index must be a DatetimeIndex")

    source_interval_minutes = interval_minutes
    for idx in range(1, len(frame.index)):
        delta_minutes = int(round((frame.index[idx] - frame.index[idx - 1]).total_seconds() / 60.0))
        if delta_minutes > 0:
            source_interval_minutes = delta_minutes
            break
    bars_per_bucket = max(1, interval_minutes // max(1, source_interval_minutes))

    aggregated: list[dict[str, Any]] = []
    current_key: tuple[date, int] | None = None
    bucket: list[tuple[pd.Timestamp, float, float, float, float, float]] = []

    def flush() -> None:
        nonlocal bucket
        if len(bucket) != bars_per_bucket:
            bucket = []
            return
        first = bucket[0]
        last = bucket[-1]
        aggregated.append(
            {
                "timestamp": last[0],
                "Open": float(first[1]),
                "High": float(max(bar[2] for bar in bucket)),
                "Low": float(min(bar[3] for bar in bucket)),
                "Close": float(last[4]),
                "Volume": float(sum(bar[5] for bar in bucket)),
            }
        )
        bucket = []

    for row in frame.itertuples(index=True, name=None):
        timestamp, open_, high, low, close, volume = row[:6]
        minutes_since_open = _minutes_since_rth_open_timestamp(timestamp)
        if minutes_since_open is None:
            continue
        key = (timestamp.date(), minutes_since_open // interval_minutes)
        if current_key is None:
            current_key = key
        if key != current_key:
            flush()
            current_key = key
        bucket.append((timestamp, float(open_), float(high), float(low), float(close), float(volume)))
    flush()

    if not aggregated:
        return frame.iloc[0:0].copy()
    resampled = pd.DataFrame(aggregated).set_index("timestamp")
    resampled.index = pd.DatetimeIndex(resampled.index)
    return resampled


class VwapPullbackTrigger(TriggerCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self._session_trade_date: date | None = None
        self._session_trades_count = 0
        self._last_exit_bar_index: int | None = None

    def load_state(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        raw_date = state.get("session_trade_date")
        self._session_trade_date = date.fromisoformat(raw_date) if raw_date else None
        self._session_trades_count = int(state.get("session_trades_count", 0))
        raw_index = state.get("last_exit_bar_index")
        self._last_exit_bar_index = int(raw_index) if raw_index is not None else None

    def dump_state(self) -> dict[str, Any]:
        return {
            "session_trade_date": self._session_trade_date.isoformat() if self._session_trade_date else None,
            "session_trades_count": self._session_trades_count,
            "last_exit_bar_index": self._last_exit_bar_index,
        }

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        session_date = context.bar.timestamp.date()
        if self._session_trade_date is None:
            self._session_trade_date = session_date
        elif self._session_trade_date != session_date:
            self._session_trade_date = session_date
            self._session_trades_count = 0
        self._last_exit_bar_index = len(context.bars) - 1
        self._session_trades_count += 1

    def _sync_session_state(self, context: StrategyContext) -> None:
        # Keep the per-session counters aligned with the current trading day even
        # when the trigger is resumed from persisted state.
        session_date = context.bar.timestamp.date()
        if self._session_trade_date is None:
            self._session_trade_date = session_date
        elif self._session_trade_date != session_date:
            self._session_trade_date = session_date
            self._session_trades_count = 0

    def _warmup_bars(self) -> int:
        return max(
            int(self.params["benchmark_ema_slow"]) * 3,
            int(self.params["trend_ema_slow"]),
            int(self.params["volume_window"]),
            int(self.params["recent_close_window"]),
            1,
        )

    def vectorbt_supported(self) -> bool:
        return True

    def _benchmark_confirmation(self, context: StrategyContext) -> bool:
        benchmark_bars = context.benchmark_bars
        if not benchmark_bars:
            return False
        benchmark_resolution_minutes = int(self.params["benchmark_resolution_minutes"])
        # Resample the benchmark to a coarser clock so the confirmation logic matches
        # the higher-level trend filter this trigger is trying to express.
        resampled = _resample_session_bars(benchmark_bars, benchmark_resolution_minutes)
        if len(resampled) < int(self.params["benchmark_ema_slow"]):
            return False
        closes = _closes(resampled)
        vwap = _session_vwap(resampled)
        ema_fast = _ema(closes, int(self.params["benchmark_ema_fast"]))
        ema_slow = _ema(closes, int(self.params["benchmark_ema_slow"]))
        if any(np.isnan(arr[-1]) for arr in (closes, vwap, ema_fast, ema_slow) if len(arr) > 0):
            return False
        if len(vwap) < 2 or np.isnan(vwap[-2]):
            return False
        return (
            float(closes[-1]) > float(vwap[-1])
            and float(ema_fast[-1]) > float(ema_slow[-1])
            and float(vwap[-1]) > float(vwap[-2])
        )

    def _trend_confirmation(self, context: StrategyContext) -> tuple[bool, float | None]:
        closes = _closes(context.bars)
        highs = _highs(context.bars)
        lows = _lows(context.bars)
        volumes = _volumes(context.bars)
        if len(closes) < self._warmup_bars():
            return False, None
        # This stack of checks is intentionally redundant: price above VWAP, EMA
        # alignment, and rising VWAP each capture a different flavor of trend health.
        vwap = _session_vwap(context.bars)
        ema_fast = _ema(closes, int(self.params["trend_ema_fast"]))
        ema_mid = _ema(closes, int(self.params["trend_ema_mid"]))
        ema_slow = _ema(closes, int(self.params["trend_ema_slow"]))
        atr = _atr(highs, lows, closes, 14)
        volume_sma = _sma(volumes, int(self.params["volume_window"]))
        if any(np.isnan(arr[-1]) for arr in (vwap, ema_fast, ema_mid, ema_slow, atr, volume_sma)):
            return False, None

        recent = int(self.params["recent_close_window"])
        above_vwap_count = sum(float(close) > float(vwap[idx]) for idx, close in enumerate(closes[-recent:], start=len(closes) - recent))
        if above_vwap_count < int(self.params["min_closes_above_vwap"]):
            return False, None
        if not (
            float(closes[-1]) > float(vwap[-1])
            and float(ema_fast[-1]) > float(ema_mid[-1]) > float(ema_slow[-1])
            and float(vwap[-1]) > float(vwap[-2])
        ):
            return False, None
        return True, float(atr[-1])

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        self._sync_session_state(context)
        if context.position.is_open:
            return StrategyDecision.hold()
        if not _bars_in_allowed_session_window(
            context.bar,
            morning_start=int(self.params["session_morning_start_minutes"]),
            morning_end=int(self.params["session_morning_end_minutes"]),
            afternoon_start=int(self.params["session_afternoon_start_minutes"]),
            afternoon_end=int(self.params["session_afternoon_end_minutes"]),
        ):
            return StrategyDecision.hold("session_window", auditor_rejection=True)
        if self._session_trades_count > 0:
            return StrategyDecision.hold("session_trade_cap", auditor_rejection=True)

        closes = _closes(context.bars)
        volumes = _volumes(context.bars)
        if len(closes) < self._warmup_bars():
            return StrategyDecision.hold("warmup")

        # Require both the broader benchmark and the traded symbol to agree before
        # the trigger considers the actual pullback entry conditions.
        benchmark_ok = self._benchmark_confirmation(context)
        trend_ok, atr_value = self._trend_confirmation(context)
        if atr_value is None:
            return StrategyDecision.hold("warmup")
        if not benchmark_ok:
            return StrategyDecision.hold("benchmark_filter", auditor_rejection=True)
        if not trend_ok:
            return StrategyDecision.hold("trend_filter", auditor_rejection=True)

        vwap = _session_vwap(context.bars)
        previous_close = float(closes[-2])
        gap_pct = abs(float(context.bar.open) - previous_close) / previous_close if previous_close > 0 else 0.0
        if gap_pct > float(self.params["max_entry_gap_pct"]):
            return StrategyDecision.hold("entry_gap", auditor_rejection=True)

        pullback_distance_pct = float(self.params["pullback_distance_pct"])
        pullback_ok = abs(float(context.bar.low) - float(vwap[-1])) / float(vwap[-1]) <= pullback_distance_pct
        previous_high = float(context.bars[-2].high)
        close_strength = _close_strength(context.bar)
        bullish_ok = float(context.bar.close) > previous_high
        close_strength_ok = close_strength >= 0.7
        avg_volume = float(np.mean(volumes[-int(self.params["volume_window"]):]))
        volume_ok = avg_volume > 0 and float(context.bar.volume) >= avg_volume * float(self.params["volume_spike_mult"])

        # The entry only fires when the bar pulls back near VWAP, but still closes
        # bullishly with enough participation to suggest the trend is resuming.
        if not pullback_ok:
            return StrategyDecision.hold("pullback_filter", auditor_rejection=True)
        if not bullish_ok:
            return StrategyDecision.hold("bullish_filter", auditor_rejection=True)
        if not close_strength_ok:
            return StrategyDecision.hold("weak_close", auditor_rejection=True)
        if not volume_ok:
            return StrategyDecision.hold("volume_filter", auditor_rejection=True)

        stop_price = min(float(context.bar.low), float(vwap[-1]) * (1.0 - float(self.params["stop_buffer_pct"])))
        entry_price = float(context.bar.close)
        stop_distance = entry_price - stop_price
        if stop_distance <= 0:
            return StrategyDecision.hold("invalid_stop", auditor_rejection=True)
        if (stop_distance / entry_price) > float(self.params["max_stop_distance_pct"]):
            return StrategyDecision.hold("stop_distance_filter", auditor_rejection=True)
        if atr_value <= 0 or stop_distance > float(self.params["max_stop_atr_mult"]) * atr_value:
            return StrategyDecision.hold("atr_stop_filter", auditor_rejection=True)

        planned_stop_pct = stop_distance / entry_price
        entry_intent = EntryIntent(
            entry_price=entry_price,
            planned_stop_pct=planned_stop_pct,
            planned_target_pct=None,
            planned_horizon_bars=12,
            signal_score=1.0,
            signal_reason="vwap_pullback",
            metadata={
                "benchmark_ok": benchmark_ok,
                "trend_ok": trend_ok,
                "pullback_ok": pullback_ok,
                "volume_ok": volume_ok,
                "close_strength": close_strength,
                "stop_price": stop_price,
                "atr_value": atr_value,
            },
        )
        return StrategyDecision.buy(float(self.params["stake"]), "vwap_pullback", entry_intent=entry_intent)

    def vectorbt_spec(self, context: VectorbtBuildContext) -> VectorbtSpec | None:
        if context.benchmark_data is None or context.data.empty:
            return None

        main_frame = context.data
        benchmark_frame = context.benchmark_data
        assert benchmark_frame is not None

        required = {"Open", "High", "Low", "Close", "Volume"}
        main_missing = sorted(required.difference(main_frame.columns))
        benchmark_missing = sorted(required.difference(benchmark_frame.columns))
        if main_missing:
            raise ValueError(f"Data frame is missing columns: {main_missing}")
        if benchmark_missing:
            raise ValueError(f"Benchmark data frame is missing columns: {benchmark_missing}")
        if not isinstance(main_frame.index, pd.DatetimeIndex):
            raise ValueError("Data frame index must be a DatetimeIndex")
        if not isinstance(benchmark_frame.index, pd.DatetimeIndex):
            raise ValueError("Benchmark data frame index must be a DatetimeIndex")
        if len(main_frame.index) == 0 or len(benchmark_frame.index) == 0:
            return None

        index = context.index
        closes = main_frame["Close"].astype(float).to_numpy()
        highs = main_frame["High"].astype(float).to_numpy()
        lows = main_frame["Low"].astype(float).to_numpy()
        opens = main_frame["Open"].astype(float).to_numpy()
        volumes = main_frame["Volume"].astype(float).to_numpy()
        vwap = _frame_session_vwap(main_frame)
        ema_fast = _ema(closes, int(self.params["trend_ema_fast"]))
        ema_mid = _ema(closes, int(self.params["trend_ema_mid"]))
        ema_slow = _ema(closes, int(self.params["trend_ema_slow"]))
        atr = _atr(highs, lows, closes, 14)
        volume_sma = _sma(volumes, int(self.params["volume_window"]))
        close_strength = _frame_close_strength(main_frame)
        prev_close = np.r_[np.nan, closes[:-1]]
        prev_high = np.r_[np.nan, highs[:-1]]

        benchmark_resolution_minutes = int(self.params["benchmark_resolution_minutes"])
        benchmark_resampled = _resample_session_frame(benchmark_frame, benchmark_resolution_minutes)
        if len(benchmark_resampled) < int(self.params["benchmark_ema_slow"]):
            return None
        benchmark_closes = benchmark_resampled["Close"].astype(float).to_numpy()
        benchmark_vwap = _frame_session_vwap(benchmark_resampled)
        benchmark_ema_fast = _ema(benchmark_closes, int(self.params["benchmark_ema_fast"]))
        benchmark_ema_slow = _ema(benchmark_closes, int(self.params["benchmark_ema_slow"]))
        benchmark_ok_resampled = (
            (benchmark_closes > benchmark_vwap)
            & (benchmark_ema_fast > benchmark_ema_slow)
            & (benchmark_vwap > np.r_[np.nan, benchmark_vwap[:-1]])
        )
        benchmark_index = benchmark_resampled.index
        benchmark_ok = (
            pd.Series(benchmark_ok_resampled, index=benchmark_index, dtype="boolean")
            .reindex(index, method="ffill")
            .fillna(False)
            .to_numpy(dtype=bool)
        )

        # Precompute the session gate once so the loop can stay focused on the
        # actual entry logic for each bar.
        session_ok = np.asarray(
            [
                _timestamp_in_allowed_session_window(
                    timestamp,
                    morning_start=int(self.params["session_morning_start_minutes"]),
                    morning_end=int(self.params["session_morning_end_minutes"]),
                    afternoon_start=int(self.params["session_afternoon_start_minutes"]),
                    afternoon_end=int(self.params["session_afternoon_end_minutes"]),
                )
                for timestamp in index
            ],
            dtype=bool,
        )

        recent_window = int(self.params["recent_close_window"])
        above_vwap_counts = np.zeros(len(main_frame), dtype=int)
        for idx in range(len(main_frame)):
            start = max(0, idx - recent_window + 1)
            recent = closes[start : idx + 1]
            recent_vwap = vwap[start : idx + 1]
            above_vwap_counts[idx] = int(np.sum(recent > recent_vwap))
        above_vwap_ok = above_vwap_counts >= int(self.params["min_closes_above_vwap"])

        pullback_ok = np.isfinite(vwap) & (np.abs(lows - vwap) / vwap <= float(self.params["pullback_distance_pct"]))
        bullish_ok = closes > prev_high
        close_strength_ok = close_strength >= 0.7
        volume_ok = np.isfinite(volume_sma) & (volumes >= volume_sma * float(self.params["volume_spike_mult"]))
        gap_ok = np.ones(len(main_frame), dtype=bool)
        if len(main_frame) > 1:
            gap_pct = np.abs(opens[1:] - prev_close[1:]) / np.where(prev_close[1:] > 0, prev_close[1:], np.nan)
            gap_ok[1:] = np.where(np.isnan(gap_pct), False, gap_pct <= float(self.params["max_entry_gap_pct"]))

        stop_price = np.minimum(lows, vwap * (1.0 - float(self.params["stop_buffer_pct"])))
        stop_distance = closes - stop_price
        stop_ok = (stop_distance > 0) & (stop_distance / closes <= float(self.params["max_stop_distance_pct"]))
        atr_ok = np.isfinite(atr) & (atr > 0) & (stop_distance <= float(self.params["max_stop_atr_mult"]) * atr)

        warmup_bars = self._warmup_bars()
        entries = np.zeros(len(main_frame), dtype=bool)
        session_trade_date: date | None = None
        session_trades_count = 0

        for idx, timestamp in enumerate(index):
            # Mirror the live trigger's one-trade-per-session behavior.
            bar_date = timestamp.date()
            if session_trade_date != bar_date:
                session_trade_date = bar_date
                session_trades_count = 0
            if idx < warmup_bars:
                continue
            minutes_since_open = _minutes_since_rth_open_timestamp(timestamp)
            if minutes_since_open is None or not session_ok[idx]:
                continue
            if session_trades_count > 0:
                continue
            if not benchmark_ok[idx]:
                continue
            if np.isnan(vwap[idx]) or np.isnan(ema_fast[idx]) or np.isnan(ema_mid[idx]) or np.isnan(ema_slow[idx]):
                continue
            if np.isnan(atr[idx]) or np.isnan(volume_sma[idx]):
                continue
            if not above_vwap_ok[idx]:
                continue
            if not (
                closes[idx] > vwap[idx]
                and ema_fast[idx] > ema_mid[idx] > ema_slow[idx]
                and vwap[idx] > vwap[idx - 1]
            ):
                continue
            if not gap_ok[idx]:
                continue
            if not pullback_ok[idx]:
                continue
            if not bullish_ok[idx]:
                continue
            if not close_strength_ok[idx]:
                continue
            if not volume_ok[idx]:
                continue
            if not stop_ok[idx]:
                continue
            if not atr_ok[idx]:
                continue

            entries[idx] = True
            session_trades_count += 1

        entries_series = pd.Series(entries, index=index)
        if isinstance(context.shared, dict):
            context.shared["entries"] = entries_series
            context.shared["size"] = float(self.params["stake"])
            context.shared["vectorbt_fill_model"] = "next_bar"

        return VectorbtSpec(
            entries=entries_series,
            size=float(self.params["stake"]),
            warmup_bars=warmup_bars,
            metadata={
                "benchmark_ok": benchmark_ok,
                "trend_ok": (
                    (closes > vwap)
                    & (ema_fast > ema_mid)
                    & (ema_mid > ema_slow)
                    & np.r_[False, vwap[1:] > vwap[:-1]]
                ),
            },
        )


def _recent_relative_volume(volumes: np.ndarray, window: int) -> tuple[float | None, float | None]:
    """Return the latest volume relative to its recent baseline, plus a z-score."""
    prior = np.asarray(volumes[-(window + 1) : -1], dtype=float)
    if prior.size < window:
        return None, None
    mean = float(np.mean(prior))
    latest = float(volumes[-1])
    if mean <= 0:
        return None, None
    std = float(np.std(prior))
    rel_volume = latest / mean
    zscore = 0.0 if std == 0 else (latest - mean) / std
    return rel_volume, float(zscore)


def _recent_realized_volatility(closes: np.ndarray, window: int) -> float | None:
    """Estimate recent realized volatility from log returns over the lookback window."""
    baseline = np.asarray(closes[-(window + 2) : -1], dtype=float)
    if baseline.size < window + 1 or np.any(baseline <= 0):
        return None
    log_returns = np.diff(np.log(baseline))
    if log_returns.size < window:
        return None
    return float(np.std(log_returns[-window:]))


def _return_burst_sigma(closes: np.ndarray, lookback: int, volatility_window: int) -> float | None:
    """Express the recent price burst as a multiple of realized volatility."""
    if len(closes) < max(lookback + 1, volatility_window + 2):
        return None
    start = float(closes[-(lookback + 1)])
    end = float(closes[-1])
    if start <= 0 or end <= 0:
        return None
    realized_vol = _recent_realized_volatility(closes, volatility_window)
    if realized_vol is None or realized_vol <= 0:
        return None
    return float(np.log(end / start) / (realized_vol * np.sqrt(float(lookback))))


class VolumeRallyTrigger(TriggerCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self._regime = RegimeClassifier(regime_params_from_strategy(params))
        self._last_exit_bar_index: int | None = None
        self._session_trade_date = None
        self._session_trades_count = 0
        self._last_entry_regime: str | None = None

    def entry_regime_label(self) -> str | None:
        return self._last_entry_regime

    def load_state(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        raw_index = state.get("last_exit_bar_index")
        self._last_exit_bar_index = int(raw_index) if raw_index is not None else None
        self._session_trade_date = state.get("session_trade_date")
        self._session_trades_count = int(state.get("session_trades_count", 0))
        self._last_entry_regime = state.get("last_entry_regime")
        self._regime.load_state(state.get("regime"))

    def dump_state(self) -> dict[str, Any]:
        return {
            "last_exit_bar_index": self._last_exit_bar_index,
            "session_trade_date": self._session_trade_date,
            "session_trades_count": self._session_trades_count,
            "last_entry_regime": self._last_entry_regime,
            "regime": self._regime.dump_state(),
        }

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        self._last_exit_bar_index = len(context.bars) - 1
        self._session_trades_count += 1

    def _sync_session_state(self, context: StrategyContext) -> None:
        # Track trades by calendar day so the session cap resets automatically on
        # the next trading date.
        session_date = str(context.bar.timestamp)[:10]
        if self._session_trade_date is None:
            self._session_trade_date = session_date
        elif self._session_trade_date != session_date:
            self._session_trade_date = session_date
            self._session_trades_count = 0

    def _in_cooldown(self, context: StrategyContext) -> bool:
        cooldown_bars = int(self.params["cooldown_bars"])
        if cooldown_bars <= 0 or self._last_exit_bar_index is None:
            return False
        bar_index = len(context.bars) - 1
        return (bar_index - self._last_exit_bar_index) < cooldown_bars

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        self._sync_session_state(context)
        if self._in_cooldown(context):
            return StrategyDecision.hold("cooldown")

        max_trades = int(self.params.get("max_trades_per_session", 0))
        if max_trades > 0 and self._session_trades_count >= max_trades:
            return StrategyDecision.hold("session_trade_cap")

        if not _in_session_window(
            context.bar,
            int(self.params.get("session_start_minutes", 0)),
            int(self.params.get("session_end_minutes", 0)),
        ):
            return StrategyDecision.hold("out_of_session_window")

        closes = _closes(context.bars)
        highs = _highs(context.bars)
        lows = _lows(context.bars)
        vols = np.asarray([bar.volume for bar in context.bars], dtype=float)

        vol_window = int(self.params["volume_window"])
        breakout_lookback = int(self.params["breakout_lookback"])
        if len(closes) < max(vol_window, breakout_lookback) + 2:
            return StrategyDecision.hold("warmup")

        vwap = _session_vwap(context.bars)
        macd_line, macd_signal, macd_hist = _macd(closes, int(self.params["macd_fast"]), int(self.params["macd_slow"]), int(self.params["macd_signal"]))
        adx = _adx(highs, lows, closes, int(self.params["adx_period"]))
        atr = _atr(highs, lows, closes, int(self.params["atr_period"]))

        if np.isnan(vwap[-1]) or np.isnan(macd_hist[-1]) or np.isnan(adx[-1]) or np.isnan(atr[-1]):
            return StrategyDecision.hold("warmup")

        avg_volume = float(np.mean(vols[-vol_window:-1]))
        volume_ok = avg_volume > 0 and float(vols[-1]) >= avg_volume * float(self.params["volume_spike_mult"])

        lookback_bars = context.bars[-(breakout_lookback + 1) : -1]
        prev_highest = max(bar.high for bar in lookback_bars)
        breakout_ok = context.bar.close > prev_highest

        vwap_ok = context.bar.close > float(vwap[-1])
        expansion_ok = _close_strength(context.bar) >= float(self.params.get("min_close_strength", 0.0))
        macd_ok = float(macd_hist[-1]) > float(macd_hist[-2]) if len(macd_hist) >= 2 else False
        adx_ok = float(adx[-1]) >= float(self.params["adx_min"])

        # The entry is deliberately multi-factor: the signal only becomes tradable
        # once enough independent confirmations are satisfied.
        entry_ok = _volume_rally_entry_signal(
            volume_ok=volume_ok,
            breakout_ok=breakout_ok,
            vwap_ok=vwap_ok,
            expansion_ok=expansion_ok,
            macd_ok=macd_ok,
            adx_ok=adx_ok,
            min_confirmations=int(self.params["min_confirmations"]),
        )
        if not entry_ok:
            return StrategyDecision.hold("no_signal")

        if not _benchmark_regime_ok(context, self.params):
            return StrategyDecision.hold("benchmark_filter")

        if bool(self.params.get("regime_enabled", False)):
            # Optional regime gating lets the strategy adapt to broader market
            # behavior without changing the base breakout signal.
            regime = self._regime.classify(context.bars)
            if not regime.is_tradeable:
                return StrategyDecision.hold("regime_filter")
            self._last_entry_regime = regime.label
        else:
            self._last_entry_regime = None

        entry_intent = atr_entry_intent(
            float(context.bar.close),
            float(atr[-1]),
            sl_mult=float(self.params["sl_atr_mult"]),
            tp_mult=float(self.params["tp_atr_mult"]),
            horizon_bars=int(self.params["max_hold_bars"]),
            signal_score=1.0,
            signal_reason="confirmed_breakout",
        )
        return StrategyDecision.buy(float(self.params["stake"]), "confirmed_breakout", entry_intent=entry_intent)


class FastUpswingTrigger(TriggerCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        highs = _highs(context.bars)
        volumes = _volumes(context.bars)
        atr = _atr(highs, _lows(context.bars), closes, int(self.params["atr_period"]))
        vwap = _session_vwap(context.bars)

        return_lookback = int(self.params["return_lookback"])
        volatility_window = int(self.params["volatility_window"])
        volume_window = int(self.params["volume_window"])
        breakout_lookback = int(self.params["breakout_lookback"])
        min_consecutive_up_bars = int(self.params["min_consecutive_up_bars"])
        adx_min = float(self.params["adx_min"])

        warmup_bars = max(
            return_lookback + 1,
            volatility_window + 2,
            volume_window + 1,
            breakout_lookback + 1 if bool(self.params["require_breakout"]) else 1,
            int(self.params["atr_period"]),
            (int(self.params["adx_period"]) * 2) if adx_min > 0 else 1,
        )
        if len(closes) < warmup_bars:
            return StrategyDecision.hold("warmup")

        atr_value = float(atr[-1]) if not np.isnan(atr[-1]) else np.nan
        if np.isnan(atr_value):
            return StrategyDecision.hold("warmup")

        consecutive_up_bars = 0
        for idx in range(len(closes) - 1, 0, -1):
            if closes[idx] > closes[idx - 1]:
                consecutive_up_bars += 1
            else:
                break

        return_burst_sigma = _return_burst_sigma(closes, return_lookback, volatility_window)
        relative_volume, volume_zscore = _recent_relative_volume(volumes, volume_window)
        if return_burst_sigma is None or relative_volume is None or volume_zscore is None:
            return StrategyDecision.hold("warmup")

        close_strength = _close_strength(context.bar)
        vwap_ok = not bool(self.params["require_vwap"]) or float(context.bar.close) > float(vwap[-1])

        breakout_ok = True
        if bool(self.params["require_breakout"]):
            lookback_bars = context.bars[-(breakout_lookback + 1) : -1]
            prev_highest = max(bar.high for bar in lookback_bars)
            breakout_ok = float(context.bar.close) > float(prev_highest)

        adx_ok = True
        adx_value = None
        if adx_min > 0:
            adx = _adx(highs, _lows(context.bars), closes, int(self.params["adx_period"]))
            adx_value = float(adx[-1]) if not np.isnan(adx[-1]) else None
            adx_ok = adx_value is not None and adx_value >= adx_min
            if adx_value is None:
                return StrategyDecision.hold("warmup")

        volume_ok = relative_volume >= float(self.params["min_relative_volume"]) or volume_zscore >= float(
            self.params["min_volume_zscore"]
        )
        burst_ok = return_burst_sigma >= float(self.params["min_return_burst_sigma"])
        up_bars_ok = consecutive_up_bars >= min_consecutive_up_bars
        close_strength_ok = close_strength >= float(self.params["min_close_strength"])

        # Build a diagnostic payload even when the trade is not taken so auditing
        # can explain which sub-checks were close and which ones blocked entry.
        signal_components: dict[str, Any] = {
            "consecutive_up_bars": consecutive_up_bars,
            "min_consecutive_up_bars": min_consecutive_up_bars,
            "return_lookback": return_lookback,
            "volatility_window": volatility_window,
            "return_burst_sigma": return_burst_sigma,
            "min_return_burst_sigma": float(self.params["min_return_burst_sigma"]),
            "relative_volume": relative_volume,
            "volume_zscore": volume_zscore,
            "min_relative_volume": float(self.params["min_relative_volume"]),
            "min_volume_zscore": float(self.params["min_volume_zscore"]),
            "close_strength": close_strength,
            "min_close_strength": float(self.params["min_close_strength"]),
            "vwap": float(vwap[-1]),
            "vwap_ok": vwap_ok,
            "breakout_ok": breakout_ok,
            "adx": adx_value,
            "adx_min": adx_min,
            "adx_ok": adx_ok,
        }
        active_components = 5 + int(bool(self.params["require_breakout"])) + int(adx_min > 0)
        true_components = sum(
            (
                up_bars_ok,
                burst_ok,
                volume_ok,
                vwap_ok,
                close_strength_ok,
                breakout_ok if bool(self.params["require_breakout"]) else False,
                adx_ok if adx_min > 0 else False,
            )
        )
        entry_intent = atr_entry_intent(
            float(context.bar.close),
            atr_value,
            sl_mult=float(self.params["sl_atr_mult"]),
            tp_mult=float(self.params["tp_atr_mult"]),
            horizon_bars=int(self.params["max_hold_bars"]),
            signal_score=true_components / float(active_components),
            signal_reason="fast_upswing",
            metadata=signal_components,
        )

        # Keep the early return reasons aligned with the diagnostic metadata above
        # so the live decision and the audit trail tell the same story.
        if not (up_bars_ok and burst_ok and volume_ok):
            return StrategyDecision.hold()
        if not close_strength_ok:
            return StrategyDecision.hold("weak_close", auditor_rejection=True, entry_intent=entry_intent)
        if not vwap_ok:
            return StrategyDecision.hold("below_vwap", auditor_rejection=True, entry_intent=entry_intent)
        if bool(self.params["require_breakout"]) and not breakout_ok:
            return StrategyDecision.hold("breakout_filter", auditor_rejection=True, entry_intent=entry_intent)
        if adx_min > 0 and not adx_ok:
            return StrategyDecision.hold("adx_filter", auditor_rejection=True, entry_intent=entry_intent)

        return StrategyDecision.buy(float(self.params["stake"]), "fast_upswing", entry_intent=entry_intent)


WarmupFn = Callable[[dict[str, Any]], int]


@dataclass(frozen=True)
class TriggerSpec:
    name: str
    description: str
    documentation: str
    params_model: type[BaseModel]
    factory: Callable[[dict[str, Any]], TriggerCore]
    warmup_bars: WarmupFn


TRIGGER_REGISTRY: dict[str, TriggerSpec] = {
    "sma_cross": TriggerSpec(
        name="sma_cross",
        description="SMA cross-up entry (long-only).",
        documentation=(
            "This trigger looks for a fast simple moving average crossing above a slower one.\n\n"
            "Use it when you want a straightforward trend-following entry rule with very little noise filtering. "
            "The trigger waits for enough bars to compute both averages, then enters long on the first confirmed cross-up.\n\n"
            "Best fit:\n"
            "- directional markets with clean momentum\n"
            "- simple baseline testing\n"
            "- strategies that rely on separate exit rules for risk management"
        ),
        params_model=SmaCrossTriggerParams,
        factory=SmaCrossTrigger,
        warmup_bars=lambda params: max(int(params["fast"]), int(params["slow"])) + 1,
    ),
    "rsi_reversion": TriggerSpec(
        name="rsi_reversion",
        description="RSI oversold entry (long-only).",
        documentation=(
            "This trigger buys when RSI falls below the oversold threshold.\n\n"
            "It is a classic mean-reversion entry: wait for momentum to look washed out, then enter long once the oscillator says the move is stretched. "
            "The trigger does not attempt to predict the rebound timing beyond that oversold condition.\n\n"
            "Best fit:\n"
            "- range-bound markets\n"
            "- pullback entries after sharp declines\n"
            "- systems that combine oscillator entries with disciplined exits"
        ),
        params_model=RsiReversionTriggerParams,
        factory=RsiReversionTrigger,
        warmup_bars=lambda params: int(params["period"]) + 1,
    ),
    "buy_and_hold": TriggerSpec(
        name="buy_and_hold",
        description="Enter once on first bar.",
        documentation=(
            "This trigger enters long on the first bar it sees and then stays out of the way.\n\n"
            "It is intentionally minimal. Use it as a benchmark, a smoke test for the execution stack, or a simple always-long reference when comparing other trigger and exit combinations."
        ),
        params_model=BuyAndHoldTriggerParams,
        factory=BuyAndHoldTrigger,
        warmup_bars=lambda params: 1,
    ),
    "breakout_channel": TriggerSpec(
        name="breakout_channel",
        description="Channel breakout entry (long-only).",
        documentation=(
            "This trigger buys when the current close breaks above the highest high of the recent lookback window.\n\n"
            "It is a clean breakout rule with very little confirmation logic. The trigger pairs well with fixed-percent exits or other protective risk rules.\n\n"
            "Best fit:\n"
            "- breakout markets\n"
            "- simple channel-trading experiments\n"
            "- quick comparisons against more filtered momentum entries"
        ),
        params_model=BreakoutChannelTriggerParams,
        factory=BreakoutChannelTrigger,
        warmup_bars=lambda params: int(params["lookback"]) + 1,
    ),
    "buy_oco_atr": TriggerSpec(
        name="buy_oco_atr",
        description="SMA cross-up entry with ATR-based intent metadata.",
        documentation=(
            "This trigger enters on an SMA cross-up and attaches ATR-based exit intent metadata to the order.\n\n"
            "Compared with plain SMA cross, it is designed for workflows that want the trigger to pre-compute a stop-loss and take-profit distance. "
            "That makes the downstream execution and reporting layer more informative without changing the underlying entry signal.\n\n"
            "Best fit:\n"
            "- trend-following setups that need structured risk metadata\n"
            "- OCO-style exits\n"
            "- strategy comparisons where entry and exit planning should stay coupled"
        ),
        params_model=BuyOcoAtrTriggerParams,
        factory=BuyOcoAtrTrigger,
        warmup_bars=lambda params: max(int(params["atr_period"]), int(params["entry_sma"])) + 1,
    ),
    "vwap_pullback": TriggerSpec(
        name="vwap_pullback",
        description="5m VWAP pullback entry with configurable benchmark confirmation.",
        documentation=(
            "This trigger buys leveraged ETFs when a strong intraday trend pulls back toward VWAP and then confirms back above the prior high.\n\n"
            "It combines a configurable benchmark-resolution filter, a 5-minute EMA stack, VWAP support, volume expansion, and a strict session window. "
            "The trigger is intended for liquid leveraged ETFs where trend continuation is strong enough to survive intraday noise.\n\n"
            "Best fit:\n"
            "- leveraged ETF continuation setups\n"
            "- VWAP pullback entries with explicit benchmark confirmation\n"
            "- intraday systems that want a single high-quality long entry per day"
        ),
        params_model=VwapPullbackTriggerParams,
        factory=VwapPullbackTrigger,
        warmup_bars=lambda params: max(
            int(params["benchmark_ema_slow"]) * 3,
            int(params["trend_ema_slow"]),
            int(params["volume_window"]),
            int(params["recent_close_window"]),
        )
        + 1,
    ),
    "volume_rally": TriggerSpec(
        name="volume_rally",
        description="Confirmed breakout trigger with optional benchmark/regime gating.",
        documentation=(
            "This trigger looks for a breakout that is supported by elevated volume and at least a configurable number of confirmation checks.\n\n"
            "The hard requirements are a breakout and a volume spike. After that, the trigger can require additional evidence from VWAP, close strength, MACD momentum, ADX trend strength, "
            "benchmark regime filters, and optional market-regime gating. The result is a more selective entry model that is designed to avoid weak breakouts.\n\n"
            "Best fit:\n"
            "- momentum strategies that should avoid low-quality breakouts\n"
            "- regimes where confirmation matters more than raw frequency\n"
            "- experiments that need explicit control over signal selectivity"
        ),
        params_model=VolumeRallyTriggerParams,
        factory=VolumeRallyTrigger,
        warmup_bars=lambda params: max(
            int(params["volume_window"]),
            int(params["breakout_lookback"]) + 1,
            int(params["atr_period"]),
            int(params["macd_slow"]) + int(params["macd_signal"]),
            int(params["adx_period"]) * 2,
            resolve_regime_warmup_bars(params),
            (
                max(int(params["benchmark_sma_period"]), int(params["benchmark_adx_period"]) * 2)
                if str(params.get("benchmark_symbol", "")).strip()
                else 0
            ),
        ),
    ),
    "fast_upswing": TriggerSpec(
        name="fast_upswing",
        description="Fast continuation entry with volume, VWAP, and volatility expansion confirmation.",
        documentation=(
            "This trigger is built for sharp continuation moves.\n\n"
            "It combines recent return acceleration, relative volume, volume z-score, consecutive up bars, close strength, VWAP confirmation, "
            "and optional breakout/ADX checks. The goal is to catch an impulsive move while it is still early, but only when several independent momentum clues line up.\n\n"
            "Best fit:\n"
            "- short-horizon continuation trades\n"
            "- momentum bursts with strong participation\n"
            "- setups where you want more structure than a naked breakout rule"
        ),
        params_model=FastUpswingTriggerParams,
        factory=FastUpswingTrigger,
        warmup_bars=lambda params: max(
            int(params["return_lookback"]) + 1,
            int(params["volatility_window"]) + 2,
            int(params["volume_window"]) + 1,
            int(params["breakout_lookback"]) + 1 if bool(params.get("require_breakout", False)) else 1,
            int(params["atr_period"]),
            (int(params["adx_period"]) * 2) if float(params.get("adx_min", 0.0)) > 0 else 1,
        ),
    ),
}


def list_triggers() -> list[TriggerSpec]:
    return list(TRIGGER_REGISTRY.values())


def get_trigger_spec(name: str) -> TriggerSpec:
    try:
        return TRIGGER_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown trigger '{name}'.") from exc


def validate_trigger_params(name: str, params: dict[str, Any] | None) -> dict[str, Any]:
    spec = get_trigger_spec(name)
    try:
        parsed = spec.params_model.model_validate(params or {})
    except ValidationError as exc:
        raise ValueError(f"Invalid params for trigger '{name}': {exc}") from exc
    return parsed.model_dump()


def resolve_trigger_warmup_bars(name: str, params: dict[str, Any]) -> int:
    return int(get_trigger_spec(name).warmup_bars(params))
