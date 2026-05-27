from __future__ import annotations

import math
from typing import Literal

import numpy as np
import pandas as pd

from app.risk.models import AmbiguousIntrabarPolicy, OutcomeLabel


def _valid_ohlc(row: pd.Series) -> bool:
    try:
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
    except (KeyError, TypeError, ValueError):
        return False
    if any(math.isnan(v) or math.isinf(v) for v in (o, h, l, c)):
        return False
    if h < l:
        return False
    if h < max(o, c) or l > min(o, c):
        return False
    return True


def _resolve_entry(
    *,
    entry_price: float,
    entry_type: str,
    fill_model: str,
    decision_idx: int,
    frame: pd.DataFrame,
) -> tuple[float, int, Literal["OK", "MISSING_BARS", "BAD_PRICE"]]:
    effective_type = entry_type
    if entry_type == "CLOSE" and fill_model == "next_bar":
        effective_type = "NEXT_OPEN"

    if effective_type == "NEXT_OPEN":
        entry_idx = decision_idx + 1
        if entry_idx >= len(frame):
            return entry_price, decision_idx, "MISSING_BARS"
        row = frame.iloc[entry_idx]
        if not _valid_ohlc(row):
            return entry_price, decision_idx, "BAD_PRICE"
        return float(row["Open"]), entry_idx, "OK"

    if not _valid_ohlc(frame.iloc[decision_idx]):
        return entry_price, decision_idx, "BAD_PRICE"
    return entry_price, decision_idx, "OK"


def label_long_candidate(
    *,
    candidate_id: str,
    label_version: str,
    entry_price: float,
    entry_type: str,
    fill_model: str,
    planned_stop_pct: float,
    planned_target_pct: float | None,
    planned_horizon_bars: int,
    decision_idx: int,
    frame: pd.DataFrame,
    atr_14_pct: float | None = None,
    ambiguous_intrabar_policy: AmbiguousIntrabarPolicy = "assume_stop_first",
) -> OutcomeLabel:
    resolved_entry, entry_idx, entry_quality = _resolve_entry(
        entry_price=entry_price,
        entry_type=entry_type,
        fill_model=fill_model,
        decision_idx=decision_idx,
        frame=frame,
    )
    if entry_quality != "OK":
        return OutcomeLabel(
            candidate_id=candidate_id,
            label_version=label_version,
            entry_price=resolved_entry,
            horizon_bars=planned_horizon_bars,
            stop_pct=planned_stop_pct,
            target_pct=planned_target_pct,
            mae_pct=0.0,
            mae_abs_pct=0.0,
            mae_atr=None,
            mfe_pct=0.0,
            final_return_pct=0.0,
            realized_R=0.0,
            hit_stop=False,
            hit_target=False,
            hit_stop_before_target=False,
            bars_held=0,
            exit_reason="DATA_ERROR",
            label_quality_flag=entry_quality,
        )

    stop_price = resolved_entry * (1.0 - planned_stop_pct)
    target_price = resolved_entry * (1.0 + planned_target_pct) if planned_target_pct is not None else None

    forward = frame.iloc[entry_idx + 1 : entry_idx + 1 + planned_horizon_bars]
    if forward.empty:
        return OutcomeLabel(
            candidate_id=candidate_id,
            label_version=label_version,
            entry_price=resolved_entry,
            horizon_bars=planned_horizon_bars,
            stop_pct=planned_stop_pct,
            target_pct=planned_target_pct,
            mae_pct=0.0,
            mae_abs_pct=0.0,
            mae_atr=None,
            mfe_pct=0.0,
            final_return_pct=0.0,
            realized_R=0.0,
            hit_stop=False,
            hit_target=False,
            hit_stop_before_target=False,
            bars_held=0,
            exit_reason="DATA_ERROR",
            label_quality_flag="MISSING_BARS",
        )

    mae_pct = 0.0
    mfe_pct = 0.0
    hit_stop = False
    hit_target = False
    bars_to_stop: int | None = None
    bars_to_target: int | None = None
    label_quality: Literal["OK", "MISSING_BARS", "BAD_PRICE", "AMBIGUOUS_INTRABAR"] = "OK"
    exit_reason: Literal["STOP", "TARGET", "TIME", "DATA_ERROR"] = "TIME"
    exit_price = float(forward.iloc[-1]["Close"])
    bars_held = len(forward)

    for offset, (_, row) in enumerate(forward.iterrows(), start=1):
        if not _valid_ohlc(row):
            return OutcomeLabel(
                candidate_id=candidate_id,
                label_version=label_version,
                entry_price=resolved_entry,
                horizon_bars=planned_horizon_bars,
                stop_pct=planned_stop_pct,
                target_pct=planned_target_pct,
                mae_pct=mae_pct,
                mae_abs_pct=abs(min(mae_pct, 0.0)),
                mae_atr=(abs(min(mae_pct, 0.0)) / atr_14_pct) if atr_14_pct else None,
                mfe_pct=mfe_pct,
                final_return_pct=0.0,
                realized_R=0.0,
                hit_stop=hit_stop,
                hit_target=hit_target,
                hit_stop_before_target=False,
                bars_held=offset - 1,
                exit_reason="DATA_ERROR",
                label_quality_flag="BAD_PRICE",
            )

        low = float(row["Low"])
        high = float(row["High"])
        bar_mae = low / resolved_entry - 1.0
        bar_mfe = high / resolved_entry - 1.0
        mae_pct = min(mae_pct, bar_mae)
        mfe_pct = max(mfe_pct, bar_mfe)

        stop_hit = low <= stop_price
        target_hit = target_price is not None and high >= target_price

        if stop_hit and target_hit:
            label_quality = "AMBIGUOUS_INTRABAR"
            if ambiguous_intrabar_policy == "assume_stop_first":
                hit_stop = True
                bars_to_stop = offset
                exit_reason = "STOP"
                exit_price = stop_price
                bars_held = offset
            else:
                hit_target = True
                bars_to_target = offset
                exit_reason = "TARGET"
                exit_price = target_price  # type: ignore[assignment]
                bars_held = offset
            break
        if stop_hit:
            hit_stop = True
            bars_to_stop = offset
            exit_reason = "STOP"
            exit_price = stop_price
            bars_held = offset
            break
        if target_hit:
            hit_target = True
            bars_to_target = offset
            exit_reason = "TARGET"
            exit_price = target_price  # type: ignore[assignment]
            bars_held = offset
            break

    final_return_pct = exit_price / resolved_entry - 1.0
    mae_abs_pct = abs(min(mae_pct, 0.0))
    realized_r = final_return_pct / planned_stop_pct if planned_stop_pct else 0.0
    hit_stop_before_target = hit_stop or (exit_reason == "TIME" and not hit_target)

    return OutcomeLabel(
        candidate_id=candidate_id,
        label_version=label_version,
        entry_price=resolved_entry,
        horizon_bars=planned_horizon_bars,
        stop_pct=planned_stop_pct,
        target_pct=planned_target_pct,
        mae_pct=mae_pct,
        mae_abs_pct=mae_abs_pct,
        mae_atr=(mae_abs_pct / atr_14_pct) if atr_14_pct else None,
        mfe_pct=mfe_pct,
        final_return_pct=final_return_pct,
        realized_R=realized_r,
        hit_stop=hit_stop,
        hit_target=hit_target,
        hit_stop_before_target=hit_stop_before_target,
        bars_to_stop=bars_to_stop,
        bars_to_target=bars_to_target,
        bars_held=bars_held,
        exit_reason=exit_reason,
        label_quality_flag=label_quality,
    )
