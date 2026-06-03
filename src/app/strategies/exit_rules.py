from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.strategies.components import ExitRuleCore
from app.strategies.core import StrategyContext, StrategyDecision
from app.strategies.implementations import (
    _adx,
    _atr,
    _bars_held,
    _closes,
    _entry_bars,
    _highs,
    _lows,
    _macd,
    _rsi,
    _sma,
    _volumes,
)
from app.strategies.regime import RegimeClassifier, regime_params_from_strategy


class ExitRuleSelection(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_rule(self) -> "ExitRuleSelection":
        if self.name not in EXIT_RULE_REGISTRY:
            available = ", ".join(sorted(EXIT_RULE_REGISTRY.keys()))
            raise ValueError(f"Unknown exit rule '{self.name}'. Available: {available}")
        self.params = validate_exit_rule_params(self.name, self.params)
        return self


class ExitRulesSelection(BaseModel):
    rules: list[ExitRuleSelection] = Field(min_length=1)

    @model_validator(mode="after")
    def ensure_unique_names(self) -> "ExitRulesSelection":
        names = [r.name for r in self.rules]
        if len(names) != len(set(names)):
            raise ValueError("exit rules must have unique names within a selection")
        return self

    def stable_id(self) -> str:
        raw = json.dumps(self.model_dump(mode="json"), sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha1(raw).hexdigest()[:10]  # noqa: S324


class FixedPctOcoParams(BaseModel):
    atr_period: int = Field(
        default=14,
        ge=2,
        title="ATR period",
        description="ATR lookback window used for rolling stop/target distances.",
    )
    sl_atr_mult: float = Field(
        default=1.5,
        gt=0,
        title="Stop loss (ATR multiple)",
        description="Stop-loss distance = ATR * sl_atr_mult.",
    )
    tp_atr_mult: float = Field(
        default=3.0,
        gt=0,
        title="Take profit (ATR multiple)",
        description="Take-profit distance = ATR * tp_atr_mult.",
    )

    @model_validator(mode="before")
    @classmethod
    def _reject_legacy_pct_params(cls, raw: Any) -> Any:
        if isinstance(raw, dict) and ("stop_loss_pct" in raw or "take_profit_pct" in raw):
            raise ValueError(
                "fixed_pct_oco now expects ATR params; use atr_period/sl_atr_mult/tp_atr_mult"
            )
        return raw


class MaxHoldBarsParams(BaseModel):
    max_hold_bars: int = Field(default=24, ge=1)


class SmaCrossDownParams(BaseModel):
    fast: int = Field(default=8, ge=2)
    slow: int = Field(default=21, ge=3)

    @model_validator(mode="after")
    def _validate_windows(self) -> "SmaCrossDownParams":
        if self.fast >= self.slow:
            raise ValueError("fast must be smaller than slow")
        return self


class RsiOverboughtParams(BaseModel):
    period: int = Field(default=14, ge=2)
    overbought: float = Field(default=60.0, ge=40, le=99)


class ChannelBreakParams(BaseModel):
    lookback: int = Field(default=20, ge=2)


class AtrOcoExitParams(BaseModel):
    atr_period: int = Field(default=14, ge=2)
    sl_atr_mult: float = Field(default=1.5, gt=0)
    tp_atr_mult: float = Field(default=3.0, gt=0)


class AtrTrailingExitParams(BaseModel):
    atr_period: int = Field(default=14, ge=2)
    trail_atr_mult: float = Field(default=1.0, gt=0)
    tp_atr_mult: float = Field(default=2.5, gt=0)


class AtrTakeProfitExitParams(BaseModel):
    atr_period: int = Field(default=14, ge=2)
    tp_atr_mult: float = Field(default=2.5, gt=0)


class AtrTrailingStopExitParams(BaseModel):
    atr_period: int = Field(default=14, ge=2)
    trail_atr_mult: float = Field(default=1.0, gt=0)


class AtrProfitProtectStopExitParams(BaseModel):
    atr_period: int = Field(
        default=14,
        ge=2,
        title="ATR period",
        description="ATR lookback window used for both the arming threshold and stop distance calculations.",
    )
    sl_atr_mult: float = Field(
        default=1.5,
        gt=0,
        title="Initial stop-loss (ATR multiple)",
        description="Before arming, stop-loss distance = ATR * sl_atr_mult below entry price.",
    )
    arm_atr_mult: float = Field(
        default=2.0,
        gt=0,
        title="Arm threshold (ATR multiple)",
        description="When close >= entry + ATR * arm_atr_mult, the rule switches from the initial stop-loss to a trailing stop.",
    )
    trail_atr_mult: float = Field(
        default=1.0,
        gt=0,
        title="Trailing stop (ATR multiple)",
        description="After arming, trailing stop = peak close since entry - ATR * trail_atr_mult (ratchets up as price makes new highs).",
    )


class VolumeRallyExitParams(BaseModel):
    atr_period: int = Field(default=14, ge=2)
    trail_atr_mult: float = Field(default=1.5, gt=0)
    tp_atr_mult: float = Field(default=3.0, gt=0)
    sl_atr_mult: float = Field(default=1.5, gt=0)
    initial_sl_atr_mult: float = Field(default=0.0, ge=0.0)
    breakeven_atr_mult: float = Field(default=0.0, ge=0.0)
    max_hold_bars: int = Field(default=48, ge=1)
    stale_bars: int = Field(default=0, ge=0)
    min_progress_atr: float = Field(default=0.5, ge=0.0)
    regime_enabled: bool = False
    volatility_regime_window: int = Field(default=0, ge=0)
    volatility_regime_max_mult: float = Field(default=2.0, gt=0)
    volatility_regime_min_mult: float = Field(default=0.5, gt=0)
    regime_adx_min: float = Field(default=25.0, ge=0.0)
    regime_slope_lookback: int = Field(default=20, ge=2)
    regime_slope_min: float = Field(default=0.0)

    @model_validator(mode="after")
    def _normalize_regime_flags(self) -> "VolumeRallyExitParams":
        if self.volatility_regime_window > 0:
            object.__setattr__(self, "regime_enabled", True)
        return self


def _should_exit_by_risk(context: StrategyContext, stop_loss_pct: float, take_profit_pct: float) -> bool:
    if not context.position.is_open or context.position.entry_price is None:
        return False
    close = context.bar.close
    stop_price = context.position.entry_price * (1.0 - stop_loss_pct)
    take_profit_price = context.position.entry_price * (1.0 + take_profit_pct)
    return close <= stop_price or close >= take_profit_price


class FixedPctOcoExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        atr = _atr(
            _highs(context.bars),
            _lows(context.bars),
            closes,
            int(self.params["atr_period"]),
        )
        if np.isnan(atr[-1]) or context.position.entry_price is None:
            return StrategyDecision.hold()
        atr_value = float(atr[-1])
        if atr_value <= 0:
            return StrategyDecision.hold()
        stop_price = float(context.position.entry_price) - atr_value * float(self.params["sl_atr_mult"])
        take_profit_price = float(context.position.entry_price) + atr_value * float(self.params["tp_atr_mult"])
        if context.bar.close <= stop_price or context.bar.close >= take_profit_price:
            return StrategyDecision.close("atr_exit")
        return StrategyDecision.hold()


class MaxHoldBarsExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        if context.position.is_open and _bars_held(context) >= int(self.params["max_hold_bars"]):
            return StrategyDecision.close("time_exit")
        return StrategyDecision.hold()


class SmaCrossDownExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        if len(closes) < 2:
            return StrategyDecision.hold()
        fast = _sma(closes, int(self.params["fast"]))
        slow = _sma(closes, int(self.params["slow"]))
        if np.isnan(fast[-1]) or np.isnan(slow[-1]) or np.isnan(fast[-2]) or np.isnan(slow[-2]):
            return StrategyDecision.hold()
        cross_down = fast[-1] < slow[-1] and fast[-2] >= slow[-2]
        if cross_down:
            return StrategyDecision.close("cross_down")
        return StrategyDecision.hold()


class RsiOverboughtExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        rsi = _rsi(closes, int(self.params["period"]))
        if np.isnan(rsi[-1]):
            return StrategyDecision.hold()
        if float(rsi[-1]) >= float(self.params["overbought"]):
            return StrategyDecision.close("overbought")
        return StrategyDecision.hold()


class ChannelBreakExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        lookback = int(self.params["lookback"])
        if len(context.bars) <= lookback:
            return StrategyDecision.hold()
        lookback_bars = context.bars[-(lookback + 1) : -1]
        prev_lowest = min(bar.low for bar in lookback_bars)
        if context.bar.close < prev_lowest:
            return StrategyDecision.close("channel_break")
        return StrategyDecision.hold()


class AtrOcoExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        atr = _atr(_highs(context.bars), _lows(context.bars), closes, int(self.params["atr_period"]))
        if np.isnan(atr[-1]) or context.position.entry_price is None:
            return StrategyDecision.hold()
        atr_value = float(atr[-1])
        if atr_value <= 0:
            return StrategyDecision.hold()
        stop_price = float(context.position.entry_price) - atr_value * float(self.params["sl_atr_mult"])
        take_profit_price = float(context.position.entry_price) + atr_value * float(self.params["tp_atr_mult"])
        if context.bar.close <= stop_price or context.bar.close >= take_profit_price:
            return StrategyDecision.close("atr_exit")
        return StrategyDecision.hold()


class AtrTrailingExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self._peak_price: float | None = None

    def load_state(self, state: dict[str, Any] | None) -> None:
        raw = (state or {}).get("peak_price")
        self._peak_price = float(raw) if raw is not None else None

    def dump_state(self) -> dict[str, Any]:
        return {"peak_price": self._peak_price}

    def on_trade_opened(self, context: StrategyContext, decision: StrategyDecision) -> None:
        self._peak_price = float(context.bar.close)

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        self._peak_price = None

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        atr = _atr(_highs(context.bars), _lows(context.bars), closes, int(self.params["atr_period"]))
        if np.isnan(atr[-1]) or context.position.entry_price is None:
            return StrategyDecision.hold()
        atr_value = float(atr[-1])
        if atr_value <= 0:
            return StrategyDecision.hold()
        if self._peak_price is None:
            self._peak_price = float(context.bar.close)
        self._peak_price = max(self._peak_price, float(context.bar.close))
        trailing_stop = self._peak_price - atr_value * float(self.params["trail_atr_mult"])
        take_profit_price = float(context.position.entry_price) + atr_value * float(self.params["tp_atr_mult"])
        if context.bar.close <= trailing_stop or context.bar.close >= take_profit_price:
            return StrategyDecision.close("trailing_exit")
        return StrategyDecision.hold()


class AtrTakeProfitExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        atr = _atr(_highs(context.bars), _lows(context.bars), closes, int(self.params["atr_period"]))
        if np.isnan(atr[-1]) or context.position.entry_price is None:
            return StrategyDecision.hold()
        atr_value = float(atr[-1])
        if atr_value <= 0:
            return StrategyDecision.hold()
        take_profit_price = float(context.position.entry_price) + atr_value * float(self.params["tp_atr_mult"])
        if context.bar.close >= take_profit_price:
            return StrategyDecision.close("atr_target")
        return StrategyDecision.hold()


class AtrTrailingStopExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self._peak_price: float | None = None

    def load_state(self, state: dict[str, Any] | None) -> None:
        raw = (state or {}).get("peak_price")
        self._peak_price = float(raw) if raw is not None else None

    def dump_state(self) -> dict[str, Any]:
        return {"peak_price": self._peak_price}

    def on_trade_opened(self, context: StrategyContext, decision: StrategyDecision) -> None:
        self._peak_price = float(context.bar.close)

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        self._peak_price = None

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        atr = _atr(_highs(context.bars), _lows(context.bars), closes, int(self.params["atr_period"]))
        if np.isnan(atr[-1]) or context.position.entry_price is None:
            return StrategyDecision.hold()
        atr_value = float(atr[-1])
        if atr_value <= 0:
            return StrategyDecision.hold()
        if self._peak_price is None:
            self._peak_price = float(context.bar.close)
        self._peak_price = max(self._peak_price, float(context.bar.close))
        trailing_stop = self._peak_price - atr_value * float(self.params["trail_atr_mult"])
        if context.bar.close <= trailing_stop:
            return StrategyDecision.close("trailing_exit")
        return StrategyDecision.hold()


class AtrProfitProtectStopExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self._armed = False
        self._peak_price: float | None = None
        self._stop_price: float | None = None

    def load_state(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        self._armed = bool(state.get("armed", False))
        raw_peak = state.get("peak_price")
        self._peak_price = float(raw_peak) if raw_peak is not None else None
        raw_stop = state.get("stop_price")
        self._stop_price = float(raw_stop) if raw_stop is not None else None

    def dump_state(self) -> dict[str, Any]:
        return {"armed": self._armed, "peak_price": self._peak_price, "stop_price": self._stop_price}

    def on_trade_opened(self, context: StrategyContext, decision: StrategyDecision) -> None:
        self._armed = False
        self._peak_price = float(context.bar.close)
        self._stop_price = None

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        self._armed = False
        self._peak_price = None
        self._stop_price = None

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        atr = _atr(_highs(context.bars), _lows(context.bars), closes, int(self.params["atr_period"]))
        if np.isnan(atr[-1]) or context.position.entry_price is None:
            return StrategyDecision.hold()
        atr_value = float(atr[-1])
        if atr_value <= 0:
            return StrategyDecision.hold()

        entry_price = float(context.position.entry_price)
        close = float(context.bar.close)

        if self._peak_price is None:
            self._peak_price = close
        self._peak_price = max(self._peak_price, close)

        if not self._armed:
            arm_price = entry_price + float(self.params["arm_atr_mult"]) * atr_value
            if close >= arm_price:
                self._armed = True

        if self._armed:
            self._stop_price = self._peak_price - atr_value * float(self.params["trail_atr_mult"])
        else:
            self._stop_price = entry_price - atr_value * float(self.params["sl_atr_mult"])

        if close <= float(self._stop_price):
            return StrategyDecision.close("atr_stop")
        return StrategyDecision.hold()


class VolumeRallyExit(ExitRuleCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params
        self._regime = RegimeClassifier(regime_params_from_strategy(params))
        self._breakeven_armed = False
        self._entry_atr: float | None = None

    def load_state(self, state: dict[str, Any] | None) -> None:
        state = state or {}
        self._breakeven_armed = bool(state.get("breakeven_armed", False))
        raw_entry_atr = state.get("entry_atr")
        self._entry_atr = float(raw_entry_atr) if raw_entry_atr is not None else None
        self._regime.load_state(state.get("regime"))

    def dump_state(self) -> dict[str, Any]:
        return {
            "breakeven_armed": self._breakeven_armed,
            "entry_atr": self._entry_atr,
            "regime": self._regime.dump_state(),
        }

    def on_trade_opened(self, context: StrategyContext, decision: StrategyDecision) -> None:
        closes = _closes(context.bars)
        highs = _highs(context.bars)
        lows = _lows(context.bars)
        atr = _atr(highs, lows, closes, int(self.params["atr_period"]))
        self._entry_atr = float(atr[-1]) if not np.isnan(atr[-1]) else None
        self._breakeven_armed = False

    def on_trade_closed(self, context: StrategyContext, decision: StrategyDecision) -> None:
        self._breakeven_armed = False
        self._entry_atr = None

    def _position_atr(self, context: StrategyContext, atr: np.ndarray) -> float:
        if self._entry_atr is not None and self._entry_atr > 0:
            return self._entry_atr
        return float(atr[-1])

    def _maybe_arm_breakeven(self, context: StrategyContext, atr_value: float) -> None:
        breakeven_mult = float(self.params["breakeven_atr_mult"])
        if breakeven_mult <= 0 or self._breakeven_armed:
            return
        entry_price = float(context.position.entry_price or 0.0)
        if context.bar.close >= entry_price + breakeven_mult * atr_value:
            self._breakeven_armed = True

    def _effective_stop(self, entry_price: float, atr_value: float) -> float:
        initial_sl_mult = float(self.params["initial_sl_atr_mult"])
        sl_mult = float(self.params["sl_atr_mult"])
        if initial_sl_mult > 0 and not self._breakeven_armed:
            stop_mult = initial_sl_mult
        else:
            stop_mult = sl_mult
        fixed_stop = entry_price - atr_value * stop_mult
        if self._breakeven_armed:
            return max(fixed_stop, entry_price)
        return fixed_stop

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        highs = _highs(context.bars)
        lows = _lows(context.bars)
        atr = _atr(highs, lows, closes, int(self.params["atr_period"]))
        if np.isnan(atr[-1]):
            return StrategyDecision.hold("warmup")

        regime = self._regime.update(context.bars)
        if context.position.is_open and regime.label == "high_vol":
            return StrategyDecision.close("regime_high_vol")

        if not context.position.is_open:
            return StrategyDecision.hold()

        atr_value = self._position_atr(context, atr)
        if atr_value <= 0:
            return StrategyDecision.hold("warmup")

        entry_price = float(context.position.entry_price or 0.0)
        stale_bars = int(self.params["stale_bars"])
        if stale_bars > 0 and _bars_held(context) >= stale_bars:
            min_progress = float(self.params["min_progress_atr"]) * atr_value
            if context.bar.close - entry_price < min_progress:
                return StrategyDecision.close("stale_exit")

        self._maybe_arm_breakeven(context, atr_value)

        entry_bars = _entry_bars(context)
        highest_close = max((bar.close for bar in entry_bars), default=context.bar.close)
        trailing_stop = highest_close - atr_value * float(self.params["trail_atr_mult"])
        effective_stop = self._effective_stop(entry_price, atr_value)
        target_price = entry_price + atr_value * float(self.params["tp_atr_mult"])
        time_exit = _bars_held(context) >= int(self.params["max_hold_bars"])

        if context.bar.close <= trailing_stop:
            return StrategyDecision.close("trailing_exit")
        if context.bar.close <= effective_stop:
            return StrategyDecision.close("atr_stop")
        if context.bar.close >= target_price:
            return StrategyDecision.close("atr_target")
        if time_exit:
            return StrategyDecision.close("time_exit")
        return StrategyDecision.hold()


WarmupFn = Callable[[dict[str, Any]], int]


@dataclass(frozen=True)
class ExitRuleSpec:
    name: str
    description: str
    params_model: type[BaseModel]
    factory: Callable[[dict[str, Any]], ExitRuleCore]
    warmup_bars: WarmupFn


EXIT_RULE_REGISTRY: dict[str, ExitRuleSpec] = {
    "fixed_pct_oco": ExitRuleSpec(
        name="fixed_pct_oco",
        description="ATR stop-loss + ATR take-profit (rolling ATR).",
        params_model=FixedPctOcoParams,
        factory=FixedPctOcoExit,
        warmup_bars=lambda params: int(params["atr_period"]) + 1,
    ),
    "max_hold_bars": ExitRuleSpec(
        name="max_hold_bars",
        description="Close after N bars held.",
        params_model=MaxHoldBarsParams,
        factory=MaxHoldBarsExit,
        warmup_bars=lambda params: 1,
    ),
    "sma_cross_down": ExitRuleSpec(
        name="sma_cross_down",
        description="Close when fast SMA crosses below slow SMA.",
        params_model=SmaCrossDownParams,
        factory=SmaCrossDownExit,
        warmup_bars=lambda params: max(int(params["fast"]), int(params["slow"])) + 1,
    ),
    "rsi_overbought": ExitRuleSpec(
        name="rsi_overbought",
        description="Close when RSI reaches overbought.",
        params_model=RsiOverboughtParams,
        factory=RsiOverboughtExit,
        warmup_bars=lambda params: int(params["period"]) + 1,
    ),
    "channel_break": ExitRuleSpec(
        name="channel_break",
        description="Close when price breaks below lookback channel low.",
        params_model=ChannelBreakParams,
        factory=ChannelBreakExit,
        warmup_bars=lambda params: int(params["lookback"]) + 1,
    ),
    "atr_oco": ExitRuleSpec(
        name="atr_oco",
        description="ATR stop-loss + ATR take-profit (OCO).",
        params_model=AtrOcoExitParams,
        factory=AtrOcoExit,
        warmup_bars=lambda params: int(params["atr_period"]) + 1,
    ),
    "atr_trailing": ExitRuleSpec(
        name="atr_trailing",
        description="ATR trailing stop + ATR take-profit.",
        params_model=AtrTrailingExitParams,
        factory=AtrTrailingExit,
        warmup_bars=lambda params: int(params["atr_period"]) + 1,
    ),
    "atr_take_profit": ExitRuleSpec(
        name="atr_take_profit",
        description="ATR take-profit only (no stop).",
        params_model=AtrTakeProfitExitParams,
        factory=AtrTakeProfitExit,
        warmup_bars=lambda params: int(params["atr_period"]) + 1,
    ),
    "atr_trailing_stop": ExitRuleSpec(
        name="atr_trailing_stop",
        description="ATR trailing stop only (no take-profit).",
        params_model=AtrTrailingStopExitParams,
        factory=AtrTrailingStopExit,
        warmup_bars=lambda params: int(params["atr_period"]) + 1,
    ),
    "atr_profit_protect_stop": ExitRuleSpec(
        name="atr_profit_protect_stop",
        description="ATR stop-loss that switches to ATR trailing after reaching an ATR-multiple profit threshold.",
        params_model=AtrProfitProtectStopExitParams,
        factory=AtrProfitProtectStopExit,
        warmup_bars=lambda params: int(params["atr_period"]) + 1,
    ),
    "volume_rally_atr": ExitRuleSpec(
        name="volume_rally_atr",
        description="Volume-rally exits: trailing/stop/target/time + optional high-vol regime exit.",
        params_model=VolumeRallyExitParams,
        factory=VolumeRallyExit,
        warmup_bars=lambda params: int(params["atr_period"]) + 1,
    ),
}


def list_exit_rules() -> list[ExitRuleSpec]:
    return list(EXIT_RULE_REGISTRY.values())


def get_exit_rule_spec(name: str) -> ExitRuleSpec:
    try:
        return EXIT_RULE_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown exit rule '{name}'.") from exc


def validate_exit_rule_params(name: str, params: dict[str, Any] | None) -> dict[str, Any]:
    spec = get_exit_rule_spec(name)
    try:
        parsed = spec.params_model.model_validate(params or {})
    except ValidationError as exc:
        raise ValueError(f"Invalid params for exit rule '{name}': {exc}") from exc
    return parsed.model_dump()


def resolve_exit_rule_warmup_bars(name: str, params: dict[str, Any]) -> int:
    return int(get_exit_rule_spec(name).warmup_bars(params))
