from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import backtrader as bt
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.strategies.implementations import (
    BreakoutChannelStrategy,
    BuyAndHoldStrategy,
    BuyOcoAtrTpSlStrategy,
    BuyOcoAtrTpTrailingStrategy,
    RsiReversionStrategy,
    SmaCrossStrategy,
)


class SmaCrossParams(BaseModel):
    fast: int = Field(default=8, ge=2)
    slow: int = Field(default=21, ge=3)
    stake: float = Field(default=1.0, gt=0)
    stop_loss_pct: float = Field(default=0.01, gt=0, lt=0.5)
    take_profit_pct: float = Field(default=0.02, gt=0, lt=1.0)
    max_hold_bars: int = Field(default=24, ge=1)

    @model_validator(mode="after")
    def _validate_windows(self) -> SmaCrossParams:
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
    def _validate_bands(self) -> RsiReversionParams:
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


@dataclass(frozen=True)
class StrategySpec:
    name: str
    description: str
    strategy_cls: type[bt.Strategy]
    params_model: type[BaseModel]


STRATEGY_REGISTRY: dict[str, StrategySpec] = {
    "sma_cross": StrategySpec(
        name="sma_cross",
        description="Intraday SMA momentum with fixed stop-loss and take-profit.",
        strategy_cls=SmaCrossStrategy,
        params_model=SmaCrossParams,
    ),
    "rsi_reversion": StrategySpec(
        name="rsi_reversion",
        description="Intraday RSI mean reversion with fixed stop-loss and take-profit.",
        strategy_cls=RsiReversionStrategy,
        params_model=RsiReversionParams,
    ),
    "buy_and_hold": StrategySpec(
        name="buy_and_hold",
        description="Single-entry long with basic stop-loss and take-profit protection.",
        strategy_cls=BuyAndHoldStrategy,
        params_model=BuyAndHoldParams,
    ),
    "breakout_channel": StrategySpec(
        name="breakout_channel",
        description="Intraday channel breakout with fixed stop-loss and take-profit.",
        strategy_cls=BreakoutChannelStrategy,
        params_model=BreakoutChannelParams,
    ),
    "buy_oco_atr_tp_sl": StrategySpec(
        name="buy_oco_atr_tp_sl",
        description="SMA-entry intraday strategy with ATR stop-loss/take-profit exits.",
        strategy_cls=BuyOcoAtrTpSlStrategy,
        params_model=BuyOcoAtrTpSlParams,
    ),
    "buy_oco_atr_tp_trailing": StrategySpec(
        name="buy_oco_atr_tp_trailing",
        description="SMA-entry intraday strategy with ATR trailing stop and ATR take-profit.",
        strategy_cls=BuyOcoAtrTpTrailingStrategy,
        params_model=BuyOcoAtrTpTrailingParams,
    ),
}


def list_strategies() -> list[StrategySpec]:
    return list(STRATEGY_REGISTRY.values())


def get_strategy_spec(name: str) -> StrategySpec:
    try:
        return STRATEGY_REGISTRY[name]
    except KeyError as exc:
        raise ValueError(f"Unknown strategy '{name}'.") from exc


def validate_strategy_params(name: str, params: dict[str, Any] | None) -> dict[str, Any]:
    spec = get_strategy_spec(name)
    try:
        parsed = spec.params_model.model_validate(params or {})
    except ValidationError as exc:
        raise ValueError(f"Invalid params for strategy '{name}': {exc}") from exc
    return parsed.model_dump()
