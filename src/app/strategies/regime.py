from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from app.strategies.core import Bar

RegimeLabel = Literal["trending", "ranging", "high_vol"]


def _sma(values: Sequence[float], period: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    out = np.full(arr.shape, np.nan, dtype=float)
    if period <= 0 or arr.size < period:
        return out
    csum = np.cumsum(arr, dtype=float)
    csum[period:] = csum[period:] - csum[:-period]
    out[period - 1 :] = csum[period - 1 :] / period
    return out


def _atr(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int) -> np.ndarray:
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


def _adx(high: Sequence[float], low: Sequence[float], close: Sequence[float], period: int) -> np.ndarray:
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    out = np.full(c.shape, np.nan, dtype=float)
    if period <= 0 or c.size < (period * 2):
        return out

    plus_dm = np.zeros_like(c)
    minus_dm = np.zeros_like(c)
    up_move = h[1:] - h[:-1]
    down_move = l[:-1] - l[1:]
    plus_dm[1:] = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm[1:] = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = np.empty_like(c)
    tr[0] = h[0] - l[0]
    tr[1:] = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])

    atr_sum = np.full_like(c, np.nan)
    plus_dm_sum = np.full_like(c, np.nan)
    minus_dm_sum = np.full_like(c, np.nan)
    atr_sum[period - 1] = np.sum(tr[:period])
    plus_dm_sum[period - 1] = np.sum(plus_dm[:period])
    minus_dm_sum[period - 1] = np.sum(minus_dm[:period])

    for i in range(period, c.size):
        atr_sum[i] = atr_sum[i - 1] - (atr_sum[i - 1] / period) + tr[i]
        plus_dm_sum[i] = plus_dm_sum[i - 1] - (plus_dm_sum[i - 1] / period) + plus_dm[i]
        minus_dm_sum[i] = minus_dm_sum[i - 1] - (minus_dm_sum[i - 1] / period) + minus_dm[i]

    plus_di = 100.0 * np.divide(plus_dm_sum, atr_sum, out=np.full_like(c, np.nan), where=atr_sum != 0)
    minus_di = 100.0 * np.divide(minus_dm_sum, atr_sum, out=np.full_like(c, np.nan), where=atr_sum != 0)
    dx = 100.0 * np.divide(
        np.abs(plus_di - minus_di),
        plus_di + minus_di,
        out=np.full_like(c, np.nan),
        where=(plus_di + minus_di) != 0,
    )

    first_adx_idx = (period * 2) - 2
    out[first_adx_idx] = np.nanmean(dx[period - 1 : first_adx_idx + 1])
    for i in range(first_adx_idx + 1, c.size):
        out[i] = ((out[i - 1] * (period - 1)) + dx[i]) / period
    return out


def _closes(bars: Sequence[Bar]) -> np.ndarray:
    return np.asarray([bar.close for bar in bars], dtype=float)


def _highs(bars: Sequence[Bar]) -> np.ndarray:
    return np.asarray([bar.high for bar in bars], dtype=float)


def _lows(bars: Sequence[Bar]) -> np.ndarray:
    return np.asarray([bar.low for bar in bars], dtype=float)


class RegimeParams(BaseModel):
    enabled: bool = True
    adx_period: int = Field(default=14, ge=2)
    adx_min: float = Field(default=20.0, ge=0.0)
    sma_period: int = Field(default=20, ge=2)
    atr_period: int = Field(default=14, ge=2)
    vol_window: int = Field(default=50, ge=2)
    vol_high_mult: float = Field(default=1.5, gt=0)
    confirmation_bars: int = Field(default=3, ge=1)


@dataclass(frozen=True)
class RegimeState:
    label: RegimeLabel
    candidate_label: RegimeLabel | None
    confirmation_count: int
    changed: bool
    bars_in_regime: int


def regime_params_from_strategy(params: dict[str, Any]) -> RegimeParams:
    legacy_window = int(params.get("volatility_regime_window", 0))
    enabled = bool(params.get("regime_enabled", False) or legacy_window > 0)
    vol_window = int(params.get("regime_vol_window", legacy_window if legacy_window > 0 else 50))
    vol_high_mult = float(
        params.get(
            "regime_vol_high_mult",
            params.get("volatility_regime_max_mult", 1.5),
        )
    )
    return RegimeParams(
        enabled=enabled,
        adx_period=int(params.get("regime_adx_period", params.get("adx_period", 14))),
        adx_min=float(params.get("regime_adx_min", 20.0)),
        sma_period=int(params.get("regime_sma_period", 20)),
        atr_period=int(params.get("regime_atr_period", params.get("atr_period", 14))),
        vol_window=vol_window,
        vol_high_mult=vol_high_mult,
        confirmation_bars=int(params.get("regime_confirmation_bars", 3)),
    )


def resolve_regime_warmup_bars(params: dict[str, Any]) -> int:
    regime = regime_params_from_strategy(params)
    if not regime.enabled:
        return 0
    return RegimeClassifier(regime).min_bars()


class RegimeClassifier:
    def __init__(self, params: RegimeParams):
        self.params = params
        self._label: RegimeLabel = "ranging"
        self._candidate_label: RegimeLabel | None = None
        self._confirmation_count = 0
        self._bars_in_regime = 0

    def min_bars(self) -> int:
        if not self.params.enabled:
            return 0
        return (
            max(
                self.params.vol_window,
                self.params.adx_period * 2,
                self.params.sma_period,
                self.params.atr_period,
            )
            + self.params.confirmation_bars
        )

    def load_state(self, state: dict[str, Any] | None) -> None:
        if not state:
            self._label = "ranging"
            self._candidate_label = None
            self._confirmation_count = 0
            self._bars_in_regime = 0
            return
        self._label = state.get("label", "ranging")
        raw_candidate = state.get("candidate_label")
        self._candidate_label = raw_candidate if raw_candidate else None
        self._confirmation_count = int(state.get("confirmation_count", 0))
        self._bars_in_regime = int(state.get("bars_in_regime", 0))

    def dump_state(self) -> dict[str, Any]:
        return {
            "label": self._label,
            "candidate_label": self._candidate_label,
            "confirmation_count": self._confirmation_count,
            "bars_in_regime": self._bars_in_regime,
        }

    def _raw_label(self, bars: Sequence[Bar]) -> RegimeLabel | None:
        closes = _closes(bars)
        highs = _highs(bars)
        lows = _lows(bars)
        atr = _atr(highs, lows, closes, self.params.atr_period)
        adx = _adx(highs, lows, closes, self.params.adx_period)
        sma = _sma(closes, self.params.sma_period)

        if (
            len(bars) < self.min_bars()
            or np.isnan(atr[-1])
            or np.isnan(adx[-1])
            or np.isnan(sma[-1])
        ):
            return None

        window = self.params.vol_window
        recent_atr = atr[-window:]
        valid_atr = recent_atr[~np.isnan(recent_atr)]
        if valid_atr.size == 0:
            return None
        median_atr = float(np.median(valid_atr))
        if median_atr <= 0:
            return None
        if float(atr[-1]) > self.params.vol_high_mult * median_atr:
            return "high_vol"

        if float(adx[-1]) >= self.params.adx_min and float(closes[-1]) > float(sma[-1]):
            return "trending"
        return "ranging"

    def update(self, bars: Sequence[Bar]) -> RegimeState:
        if not self.params.enabled:
            return RegimeState(
                label="trending",
                candidate_label=None,
                confirmation_count=0,
                changed=False,
                bars_in_regime=self._bars_in_regime,
            )

        raw_label = self._raw_label(bars)
        if raw_label is None:
            return RegimeState(
                label=self._label,
                candidate_label=self._candidate_label,
                confirmation_count=self._confirmation_count,
                changed=False,
                bars_in_regime=self._bars_in_regime,
            )

        changed = False
        if raw_label == self._label:
            self._candidate_label = None
            self._confirmation_count = 0
            self._bars_in_regime += 1
        else:
            if raw_label == self._candidate_label:
                self._confirmation_count += 1
            else:
                self._candidate_label = raw_label
                self._confirmation_count = 1
            if self._confirmation_count >= self.params.confirmation_bars:
                self._label = raw_label
                self._candidate_label = None
                self._confirmation_count = 0
                self._bars_in_regime = 1
                changed = True

        return RegimeState(
            label=self._label,
            candidate_label=self._candidate_label,
            confirmation_count=self._confirmation_count,
            changed=changed,
            bars_in_regime=self._bars_in_regime,
        )
