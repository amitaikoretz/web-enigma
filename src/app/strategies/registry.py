from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError, model_validator

from app.strategies.core import StrategyDefinition
from app.strategies.regime import resolve_regime_warmup_bars
from app.strategies.implementations import (
    BreakoutChannelCore,
    BuyAndHoldCore,
    BuyOcoAtrTpSlCore,
    BuyOcoAtrTpTrailingCore,
    RsiReversionCore,
    SmaCrossCore,
    VolumeRallyCore,
)


class SmaCrossParams(BaseModel):
    fast: int = Field(default=8, ge=2)
    slow: int = Field(default=21, ge=3)
    stake: float = Field(default=1.0, gt=0)
    stop_loss_pct: float = Field(default=0.01, gt=0, lt=0.5)
    take_profit_pct: float = Field(default=0.02, gt=0, lt=1.0)
    max_hold_bars: int = Field(default=24, ge=1)

    @model_validator(mode="after")
    def _validate_windows(self) -> "SmaCrossParams":
        if self.fast >= self.slow:
            raise ValueError("fast must be smaller than slow")
        return self


class RsiReversionParams(BaseModel):
    period: int = Field(default=14, ge=2)
    oversold: float = Field(default=30.0, ge=1, le=60)
    overbought: float = Field(default=60.0, ge=40, le=99)
    stake: float = Field(default=1.0, gt=0)
    stop_loss_pct: float = Field(default=0.008, gt=0, lt=0.5)
    take_profit_pct: float = Field(default=0.015, gt=0, lt=1.0)
    max_hold_bars: int = Field(default=18, ge=1)

    @model_validator(mode="after")
    def _validate_bands(self) -> "RsiReversionParams":
        if self.oversold >= self.overbought:
            raise ValueError("oversold must be smaller than overbought")
        return self


class BuyAndHoldParams(BaseModel):
    stake: float = Field(default=1.0, gt=0)
    stop_loss_pct: float = Field(default=0.02, gt=0, lt=0.5)
    take_profit_pct: float = Field(default=0.04, gt=0, lt=1.0)


class BreakoutChannelParams(BaseModel):
    lookback: int = Field(default=20, ge=2)
    stake: float = Field(default=1.0, gt=0)
    stop_loss_pct: float = Field(default=0.01, gt=0, lt=0.5)
    take_profit_pct: float = Field(default=0.02, gt=0, lt=1.0)
    max_hold_bars: int = Field(default=20, ge=1)


class BuyOcoAtrTpSlParams(BaseModel):
    stake: float = Field(default=1.0, gt=0)
    atr_period: int = Field(default=14, ge=2)
    entry_sma: int = Field(default=20, ge=2)
    sl_atr_mult: float = Field(default=1.5, gt=0)
    tp_atr_mult: float = Field(default=3.0, gt=0)
    max_hold_bars: int = Field(default=24, ge=1)


class BuyOcoAtrTpTrailingParams(BaseModel):
    stake: float = Field(default=1.0, gt=0)
    atr_period: int = Field(default=14, ge=2)
    entry_sma: int = Field(default=20, ge=2)
    trail_atr_mult: float = Field(default=1.0, gt=0)
    tp_atr_mult: float = Field(default=2.5, gt=0)
    max_hold_bars: int = Field(default=30, ge=1)


class VolumeRallyParams(BaseModel):
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
    trail_atr_mult: float = Field(default=1.5, gt=0)
    max_hold_bars: int = Field(default=48, ge=1)
    cooldown_bars: int = Field(default=0, ge=0)
    session_start_minutes: int = Field(default=0, ge=0)
    session_end_minutes: int = Field(default=0, ge=0)
    min_close_strength: float = Field(default=0.0, ge=0.0, le=1.0)
    max_trades_per_session: int = Field(default=0, ge=0)
    initial_sl_atr_mult: float = Field(default=0.0, ge=0.0)
    breakeven_atr_mult: float = Field(default=0.0, ge=0.0)
    stale_bars: int = Field(default=0, ge=0)
    min_progress_atr: float = Field(default=0.5, ge=0.0)
    min_confirmations: int = Field(
        default=3,
        ge=2,
        le=6,
        description=(
            "Minimum entry confirmations. Volume spike and breakout are always required; "
            "the remaining filters (VWAP, expansion, MACD, ADX) count toward this total. "
            "6 requires all filters (legacy behavior)."
        ),
    )
    volatility_regime_window: int = Field(
        default=0,
        ge=0,
        description="Legacy: when > 0, enables regime gating and maps to regime_vol_window.",
    )
    volatility_regime_max_mult: float = Field(default=2.0, gt=0)
    volatility_regime_min_mult: float = Field(default=0.5, gt=0)
    regime_enabled: bool = Field(
        default=False,
        description="Enable market regime gating (trending/ranging/high_vol). Also enabled when volatility_regime_window > 0.",
    )
    regime_adx_min: float = Field(default=20.0, ge=0.0)
    regime_sma_period: int = Field(default=20, ge=2)
    regime_vol_window: int = Field(default=50, ge=2)
    regime_vol_high_mult: float = Field(default=1.5, gt=0)
    regime_confirmation_bars: int = Field(default=3, ge=1)
    benchmark_symbol: str = Field(
        default="",
        description="Benchmark symbol for market regime filter (e.g. SPY). Empty disables the filter.",
    )
    benchmark_sma_period: int = Field(default=20, ge=2)
    benchmark_adx_period: int = Field(default=14, ge=2)
    benchmark_adx_min: float = Field(default=25.0, ge=0.0)
    benchmark_require_above_sma: bool = Field(default=True)

    @model_validator(mode="after")
    def _validate_windows(self) -> "VolumeRallyParams":
        if self.macd_fast >= self.macd_slow:
            raise ValueError("macd_fast must be smaller than macd_slow")
        if self.benchmark_symbol.strip() and not self.benchmark_require_above_sma and self.benchmark_adx_min <= 0:
            raise ValueError("benchmark filter requires benchmark_require_above_sma or benchmark_adx_min > 0")
        return self


WarmupFn = Callable[[dict[str, Any]], int]


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    params_model: type[BaseModel]
    factory: Callable[[dict[str, Any]], Any]
    warmup_bars: WarmupFn

    def to_definition(self) -> StrategyDefinition:
        return StrategyDefinition(
            name=self.name,
            description=self.description,
            params_model=self.params_model,
            factory=self.factory,
            warmup_bars=self.warmup_bars,
        )


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "sma_cross": StrategySpec(
        name="sma_cross",
        description="Intraday SMA momentum with fixed stop-loss and take-profit.",
        params_model=SmaCrossParams,
        factory=SmaCrossCore,
        warmup_bars=lambda params: max(int(params["fast"]), int(params["slow"])) + 1,
    ),
    "rsi_reversion": StrategySpec(
        name="rsi_reversion",
        description="Intraday RSI mean reversion with fixed stop-loss and take-profit.",
        params_model=RsiReversionParams,
        factory=RsiReversionCore,
        warmup_bars=lambda params: int(params["period"]) + 1,
    ),
    "buy_and_hold": StrategySpec(
        name="buy_and_hold",
        description="Single-entry long with basic stop-loss and take-profit protection.",
        params_model=BuyAndHoldParams,
        factory=BuyAndHoldCore,
        warmup_bars=lambda params: 1,
    ),
    "breakout_channel": StrategySpec(
        name="breakout_channel",
        description="Intraday channel breakout with fixed stop-loss and take-profit.",
        params_model=BreakoutChannelParams,
        factory=BreakoutChannelCore,
        warmup_bars=lambda params: int(params["lookback"]) + 1,
    ),
    "buy_oco_atr_tp_sl": StrategySpec(
        name="buy_oco_atr_tp_sl",
        description="SMA-entry intraday strategy with ATR stop-loss/take-profit exits.",
        params_model=BuyOcoAtrTpSlParams,
        factory=BuyOcoAtrTpSlCore,
        warmup_bars=lambda params: max(int(params["atr_period"]), int(params["entry_sma"])) + 1,
    ),
    "buy_oco_atr_tp_trailing": StrategySpec(
        name="buy_oco_atr_tp_trailing",
        description="SMA-entry intraday strategy with ATR trailing stop and ATR take-profit.",
        params_model=BuyOcoAtrTpTrailingParams,
        factory=BuyOcoAtrTpTrailingCore,
        warmup_bars=lambda params: max(int(params["atr_period"]), int(params["entry_sma"])) + 1,
    ),
    "volume_rally": StrategySpec(
        name="volume_rally",
        description=(
            "Confirmed breakout/rally with tiered entry filters (volume + breakout required, "
            "plus min_confirmations of VWAP/expansion/MACD/ADX), optional market-regime gating and "
            "benchmark (SPY/QQQ) filters, and ATR exits. "
            "Optional session window, close-strength filter, per-session trade cap, breakeven floor, and stale-trade exit."
        ),
        params_model=VolumeRallyParams,
        factory=VolumeRallyCore,
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


def list_strategies() -> list[StrategySpec]:
    return list(STRATEGY_REGISTRY.values())


def get_strategy_spec(name: str) -> StrategySpec:
    try:
        return STRATEGY_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown strategy '{name}'.") from exc


def get_strategy_definition(name: str) -> StrategyDefinition:
    return get_strategy_spec(name).to_definition()


def resolve_warmup_bars(name: str, params: dict[str, Any]) -> int:
    return int(get_strategy_spec(name).warmup_bars(params))


def validate_strategy_params(name: str, params: dict[str, Any] | None) -> dict[str, Any]:
    spec = get_strategy_spec(name)
    try:
        parsed = spec.params_model.model_validate(params or {})
    except ValidationError as exc:
        raise ValueError(f"Invalid params for strategy '{name}': {exc}") from exc
    return parsed.model_dump()
