from __future__ import annotations

from typing import Any

from app.strategies.candidates import EntryIntent
from app.strategies.core import StrategyContext


def fixed_pct_entry_intent(
    context: StrategyContext,
    params: dict[str, Any],
    *,
    signal_score: float | None,
    signal_reason: str | None,
    metadata: dict[str, Any] | None = None,
) -> EntryIntent:
    return EntryIntent(
        entry_price=float(context.bar.close),
        planned_stop_pct=float(params["stop_loss_pct"]),
        planned_target_pct=float(params["take_profit_pct"]),
        planned_horizon_bars=int(params["max_hold_bars"]),
        signal_score=signal_score,
        signal_reason=signal_reason,
        metadata=dict(metadata or {}),
    )


def atr_entry_intent(
    entry_price: float,
    atr_value: float,
    *,
    sl_mult: float,
    tp_mult: float,
    horizon_bars: int,
    signal_score: float | None,
    signal_reason: str | None,
    metadata: dict[str, Any] | None = None,
) -> EntryIntent:
    stop_price = entry_price - atr_value * sl_mult
    target_price = entry_price + atr_value * tp_mult
    planned_stop_pct = max(0.0, (entry_price - stop_price) / entry_price)
    planned_target_pct = max(0.0, (target_price - entry_price) / entry_price)
    return EntryIntent(
        entry_price=entry_price,
        planned_stop_pct=planned_stop_pct,
        planned_target_pct=planned_target_pct,
        planned_horizon_bars=horizon_bars,
        signal_score=signal_score,
        signal_reason=signal_reason,
        metadata=dict(metadata or {}),
    )
