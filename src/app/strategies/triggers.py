from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.strategies.components import TriggerCore
from app.strategies.core import StrategyContext, StrategyDecision
from app.strategies.entry_plans import atr_entry_intent, fixed_pct_entry_intent
from app.strategies.implementations import (
    _adx,
    _atr,
    _benchmark_regime_ok,
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
    _volume_rally_entry_signal,
    _volumes,
)
from app.strategies.regime import RegimeClassifier, regime_params_from_strategy, resolve_regime_warmup_bars


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
    fast: int = Field(default=8, ge=2)
    slow: int = Field(default=21, ge=3)
    stake: float = Field(default=1.0, gt=0)

    @model_validator(mode="after")
    def _validate_windows(self) -> "SmaCrossTriggerParams":
        if self.fast >= self.slow:
            raise ValueError("fast must be smaller than slow")
        return self


class RsiReversionTriggerParams(BaseModel):
    period: int = Field(default=14, ge=2)
    oversold: float = Field(default=30.0, ge=1, le=60)
    stake: float = Field(default=1.0, gt=0)


class BuyAndHoldTriggerParams(BaseModel):
    stake: float = Field(default=1.0, gt=0)


class BreakoutChannelTriggerParams(BaseModel):
    lookback: int = Field(default=20, ge=2)
    stake: float = Field(default=1.0, gt=0)
    stop_loss_pct: float = Field(default=0.01, gt=0, lt=0.5)
    take_profit_pct: float = Field(default=0.02, gt=0, lt=1.0)
    max_hold_bars: int = Field(default=20, ge=1)


class BuyOcoAtrTriggerParams(BaseModel):
    stake: float = Field(default=1.0, gt=0)
    atr_period: int = Field(default=14, ge=2)
    entry_sma: int = Field(default=20, ge=2)
    sl_atr_mult: float = Field(default=1.5, gt=0)
    tp_atr_mult: float = Field(default=3.0, gt=0)
    max_hold_bars: int = Field(default=24, ge=1)


class VolumeRallyTriggerParams(BaseModel):
    stake: float = Field(default=1.0, gt=0)
    volume_window: int = Field(default=20, ge=2)
    volume_spike_mult: float = Field(default=3.0, gt=0)
    breakout_lookback: int = Field(default=20, ge=2)
    atr_period: int = Field(default=14, ge=2)
    atr_expansion_mult: float = Field(default=0.5, gt=0)
    macd_fast: int = Field(default=12, ge=2)
    macd_slow: int = Field(default=26, ge=3)
    macd_signal: int = Field(default=9, ge=2)
    adx_period: int = Field(default=14, ge=2)
    adx_min: float = Field(default=25.0, ge=0.0)
    sl_atr_mult: float = Field(default=1.5, gt=0)
    tp_atr_mult: float = Field(default=3.0, gt=0)
    max_hold_bars: int = Field(default=48, ge=1)
    stale_bars: int = Field(default=0, ge=0)
    cooldown_bars: int = Field(default=0, ge=0)
    session_start_minutes: int = Field(default=0, ge=0)
    session_end_minutes: int = Field(default=0, ge=0)
    min_close_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    max_trades_per_session: int = Field(default=0, ge=0)
    min_confirmations: int = Field(default=3, ge=2, le=6)
    regime_enabled: bool = False
    volatility_regime_window: int = Field(default=0, ge=0)
    volatility_regime_max_mult: float = Field(default=2.0, gt=0)
    volatility_regime_min_mult: float = Field(default=0.5, gt=0)
    regime_adx_min: float = Field(default=25.0, ge=0.0)
    regime_slope_lookback: int = Field(default=20, ge=2)
    regime_slope_min: float = Field(default=0.0)
    benchmark_symbol: str = ""
    benchmark_sma_period: int = Field(default=20, ge=2)
    benchmark_adx_period: int = Field(default=14, ge=2)
    benchmark_adx_min: float = Field(default=25.0, ge=0.0)
    benchmark_require_above_sma: bool = True

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
    stake: float = Field(default=1.0, gt=0)
    return_lookback: int = Field(default=5, ge=2)
    volatility_window: int = Field(default=20, ge=2)
    min_return_burst_sigma: float = Field(default=1.0, gt=0.0)
    volume_window: int = Field(default=20, ge=2)
    min_relative_volume: float = Field(default=1.5, gt=0.0)
    min_volume_zscore: float = Field(default=1.0, gt=0.0)
    min_consecutive_up_bars: int = Field(default=3, ge=2)
    min_close_strength: float = Field(default=0.65, ge=0.0, le=1.0)
    require_vwap: bool = True
    breakout_lookback: int = Field(default=5, ge=2)
    require_breakout: bool = False
    atr_period: int = Field(default=14, ge=2)
    sl_atr_mult: float = Field(default=1.5, gt=0)
    tp_atr_mult: float = Field(default=3.0, gt=0)
    max_hold_bars: int = Field(default=24, ge=1)
    adx_period: int = Field(default=14, ge=2)
    adx_min: float = Field(default=0.0, ge=0.0)


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

    def load_state(self, state: dict[str, Any] | None) -> None:
        self.has_entered = bool((state or {}).get("has_entered", False))

    def dump_state(self) -> dict[str, Any]:
        return {"has_entered": self.has_entered}

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


def _recent_relative_volume(volumes: np.ndarray, window: int) -> tuple[float | None, float | None]:
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
    baseline = np.asarray(closes[-(window + 2) : -1], dtype=float)
    if baseline.size < window + 1 or np.any(baseline <= 0):
        return None
    log_returns = np.diff(np.log(baseline))
    if log_returns.size < window:
        return None
    return float(np.std(log_returns[-window:]))


def _return_burst_sigma(closes: np.ndarray, lookback: int, volatility_window: int) -> float | None:
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
    params_model: type[BaseModel]
    factory: Callable[[dict[str, Any]], TriggerCore]
    warmup_bars: WarmupFn


TRIGGER_REGISTRY: dict[str, TriggerSpec] = {
    "sma_cross": TriggerSpec(
        name="sma_cross",
        description="SMA cross-up entry (long-only).",
        params_model=SmaCrossTriggerParams,
        factory=SmaCrossTrigger,
        warmup_bars=lambda params: max(int(params["fast"]), int(params["slow"])) + 1,
    ),
    "rsi_reversion": TriggerSpec(
        name="rsi_reversion",
        description="RSI oversold entry (long-only).",
        params_model=RsiReversionTriggerParams,
        factory=RsiReversionTrigger,
        warmup_bars=lambda params: int(params["period"]) + 1,
    ),
    "buy_and_hold": TriggerSpec(
        name="buy_and_hold",
        description="Enter once on first bar.",
        params_model=BuyAndHoldTriggerParams,
        factory=BuyAndHoldTrigger,
        warmup_bars=lambda params: 1,
    ),
    "breakout_channel": TriggerSpec(
        name="breakout_channel",
        description="Channel breakout entry (long-only).",
        params_model=BreakoutChannelTriggerParams,
        factory=BreakoutChannelTrigger,
        warmup_bars=lambda params: int(params["lookback"]) + 1,
    ),
    "buy_oco_atr": TriggerSpec(
        name="buy_oco_atr",
        description="SMA cross-up entry with ATR-based intent metadata.",
        params_model=BuyOcoAtrTriggerParams,
        factory=BuyOcoAtrTrigger,
        warmup_bars=lambda params: max(int(params["atr_period"]), int(params["entry_sma"])) + 1,
    ),
    "volume_rally": TriggerSpec(
        name="volume_rally",
        description="Confirmed breakout trigger with optional benchmark/regime gating.",
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
