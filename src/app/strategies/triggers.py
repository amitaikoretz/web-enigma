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
