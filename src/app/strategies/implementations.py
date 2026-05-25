from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import numpy as np
from backtesting import Strategy

from app.strategies.core import Bar, ExecutionEvent, PositionState, StrategyContext, StrategyCore, StrategyDecision


def _sma(values: Sequence[float], period: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    out = np.full(arr.shape, np.nan, dtype=float)
    if period <= 0 or arr.size < period:
        return out
    csum = np.cumsum(arr, dtype=float)
    csum[period:] = csum[period:] - csum[:-period]
    out[period - 1 :] = csum[period - 1 :] / period
    return out


def _rsi(values: Sequence[float], period: int) -> np.ndarray:
    close = np.asarray(values, dtype=float)
    out = np.full(close.shape, np.nan, dtype=float)
    if period <= 0 or close.size <= period:
        return out
    delta = np.diff(close)
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)

    avg_gain = np.empty_like(close)
    avg_loss = np.empty_like(close)
    avg_gain[:] = np.nan
    avg_loss[:] = np.nan

    avg_gain[period] = np.mean(gains[:period])
    avg_loss[period] = np.mean(losses[:period])

    for i in range(period + 1, close.size):
        avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i - 1]) / period
        avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i - 1]) / period

    rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.nan), where=avg_loss != 0)
    out = 100.0 - (100.0 / (1.0 + rs))
    out[np.isnan(avg_loss)] = np.nan
    out[(avg_loss == 0) & (~np.isnan(avg_gain))] = 100.0
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


def _ema(values: Sequence[float], period: int) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    out = np.full(arr.shape, np.nan, dtype=float)
    valid_indices = np.flatnonzero(~np.isnan(arr))
    if period <= 0 or valid_indices.size < period:
        return out
    alpha = 2.0 / (period + 1.0)
    seed_indices = valid_indices[:period]
    seed_end = int(seed_indices[-1])
    out[seed_end] = float(np.mean(arr[seed_indices]))
    prev = out[seed_end]
    for i in valid_indices[period:]:
        prev = alpha * arr[i] + (1.0 - alpha) * prev
        out[i] = prev
    return out


def _session_vwap(bars: Sequence[Bar]) -> np.ndarray:
    typical_price = np.asarray([(bar.high + bar.low + bar.close) / 3.0 for bar in bars], dtype=float)
    volume = np.asarray([bar.volume for bar in bars], dtype=float)
    out = np.full(len(bars), np.nan, dtype=float)
    cumulative_volume = 0.0
    cumulative_turnover = 0.0
    session_date = None
    for idx, bar in enumerate(bars):
        bar_date = bar.timestamp.date()
        if session_date is not None and bar_date != session_date:
            cumulative_volume = 0.0
            cumulative_turnover = 0.0
        session_date = bar_date
        cumulative_volume += float(volume[idx])
        cumulative_turnover += float(typical_price[idx] * volume[idx])
        if cumulative_volume != 0:
            out[idx] = cumulative_turnover / cumulative_volume
    return out


def _macd(values: Sequence[float], fast: int, slow: int, signal: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    fast_ema = _ema(values, fast)
    slow_ema = _ema(values, slow)
    macd_line = fast_ema - slow_ema
    signal_line = _ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


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


def _volumes(bars: Sequence[Bar]) -> np.ndarray:
    return np.asarray([bar.volume for bar in bars], dtype=float)


def _entry_bars(context: StrategyContext) -> Sequence[Bar]:
    if context.position.entry_bar_index is not None:
        start = max(0, context.position.entry_bar_index)
        return context.bars[start:]
    if context.position.entry_time is None:
        return []
    for idx, bar in enumerate(context.bars):
        if bar.iso_timestamp == context.position.entry_time:
            return context.bars[idx:]
    return []


def _bars_held(context: StrategyContext) -> int:
    if not context.position.is_open:
        return 0
    if context.position.bars_held:
        return context.position.bars_held
    bars = _entry_bars(context)
    return max(0, len(bars) - 1)


def _should_exit_by_risk(context: StrategyContext, stop_loss_pct: float, take_profit_pct: float) -> bool:
    if not context.position.is_open or context.position.entry_price is None:
        return False
    close = context.bar.close
    stop_price = context.position.entry_price * (1.0 - stop_loss_pct)
    take_profit_price = context.position.entry_price * (1.0 + take_profit_pct)
    return close <= stop_price or close >= take_profit_price


class BasePortableStrategy(StrategyCore):
    def __init__(self, params: dict[str, Any]):
        self.params = params


class SmaCrossCore(BasePortableStrategy):
    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        if len(closes) < 2:
            return StrategyDecision.hold("need_more_bars")
        fast = _sma(closes, int(self.params["fast"]))
        slow = _sma(closes, int(self.params["slow"]))
        if np.isnan(fast[-1]) or np.isnan(slow[-1]) or np.isnan(fast[-2]) or np.isnan(slow[-2]):
            return StrategyDecision.hold("warmup")

        cross_up = fast[-1] > slow[-1] and fast[-2] <= slow[-2]
        cross_down = fast[-1] < slow[-1] and fast[-2] >= slow[-2]

        if context.position.is_open:
            time_exit = _bars_held(context) >= int(self.params["max_hold_bars"])
            risk_exit = _should_exit_by_risk(
                context,
                float(self.params["stop_loss_pct"]),
                float(self.params["take_profit_pct"]),
            )
            if cross_down:
                return StrategyDecision.close("cross_down")
            if risk_exit:
                return StrategyDecision.close("risk_exit")
            if time_exit:
                return StrategyDecision.close("time_exit")
            return StrategyDecision.hold()

        if cross_up:
            return StrategyDecision.buy(float(self.params["stake"]), "cross_up")
        return StrategyDecision.hold()


class RsiReversionCore(BasePortableStrategy):
    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        rsi = _rsi(closes, int(self.params["period"]))
        if np.isnan(rsi[-1]):
            return StrategyDecision.hold("warmup")

        if context.position.is_open:
            time_exit = _bars_held(context) >= int(self.params["max_hold_bars"])
            signal_exit = float(rsi[-1]) >= float(self.params["overbought"])
            risk_exit = _should_exit_by_risk(
                context,
                float(self.params["stop_loss_pct"]),
                float(self.params["take_profit_pct"]),
            )
            if signal_exit:
                return StrategyDecision.close("overbought")
            if risk_exit:
                return StrategyDecision.close("risk_exit")
            if time_exit:
                return StrategyDecision.close("time_exit")
            return StrategyDecision.hold()

        if float(rsi[-1]) <= float(self.params["oversold"]):
            return StrategyDecision.buy(float(self.params["stake"]), "oversold")
        return StrategyDecision.hold()


class BuyAndHoldCore(BasePortableStrategy):
    def __init__(self, params: dict[str, Any]):
        super().__init__(params)
        self.has_entered = False

    def load_state(self, state: dict[str, Any] | None) -> None:
        self.has_entered = bool((state or {}).get("has_entered", False))

    def dump_state(self) -> dict[str, Any]:
        return {"has_entered": self.has_entered}

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        if context.position.is_open:
            if _should_exit_by_risk(
                context,
                float(self.params["stop_loss_pct"]),
                float(self.params["take_profit_pct"]),
            ):
                return StrategyDecision.close("risk_exit")
            return StrategyDecision.hold()

        if not self.has_entered:
            self.has_entered = True
            return StrategyDecision.buy(float(self.params["stake"]), "initial_entry")
        return StrategyDecision.hold()


class BuyOcoAtrTpSlCore(BasePortableStrategy):
    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        if len(closes) < 2:
            return StrategyDecision.hold("need_more_bars")
        atr = _atr(_highs(context.bars), _lows(context.bars), closes, int(self.params["atr_period"]))
        sma = _sma(closes, int(self.params["entry_sma"]))
        if np.isnan(sma[-1]) or np.isnan(sma[-2]) or np.isnan(atr[-1]):
            return StrategyDecision.hold("warmup")

        cross_up = closes[-1] > sma[-1] and closes[-2] <= sma[-2]
        cross_down = closes[-1] < sma[-1] and closes[-2] >= sma[-2]

        if context.position.is_open:
            time_exit = _bars_held(context) >= int(self.params["max_hold_bars"])
            atr_value = float(atr[-1])
            atr_exit = False
            if context.position.entry_price is not None and atr_value > 0:
                stop_price = context.position.entry_price - atr_value * float(self.params["sl_atr_mult"])
                take_profit_price = context.position.entry_price + atr_value * float(self.params["tp_atr_mult"])
                atr_exit = context.bar.close <= stop_price or context.bar.close >= take_profit_price
            if cross_down:
                return StrategyDecision.close("cross_down")
            if atr_exit:
                return StrategyDecision.close("atr_exit")
            if time_exit:
                return StrategyDecision.close("time_exit")
            return StrategyDecision.hold()

        if cross_up:
            return StrategyDecision.buy(float(self.params["stake"]), "cross_up")
        return StrategyDecision.hold()


class BuyOcoAtrTpTrailingCore(BasePortableStrategy):
    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        if len(closes) < 2:
            return StrategyDecision.hold("need_more_bars")
        atr = _atr(_highs(context.bars), _lows(context.bars), closes, int(self.params["atr_period"]))
        sma = _sma(closes, int(self.params["entry_sma"]))
        if np.isnan(sma[-1]) or np.isnan(sma[-2]) or np.isnan(atr[-1]):
            return StrategyDecision.hold("warmup")

        cross_up = closes[-1] > sma[-1] and closes[-2] <= sma[-2]
        cross_down = closes[-1] < sma[-1] and closes[-2] >= sma[-2]

        if context.position.is_open:
            time_exit = _bars_held(context) >= int(self.params["max_hold_bars"])
            atr_value = float(atr[-1])
            trailing_exit = False
            if context.position.entry_price is not None and atr_value > 0:
                entry_bars = _entry_bars(context)
                peak_price = max((bar.close for bar in entry_bars), default=context.bar.close)
                trailing_stop = peak_price - atr_value * float(self.params["trail_atr_mult"])
                take_profit_price = context.position.entry_price + atr_value * float(self.params["tp_atr_mult"])
                trailing_exit = context.bar.close <= trailing_stop or context.bar.close >= take_profit_price
            if cross_down:
                return StrategyDecision.close("cross_down")
            if trailing_exit:
                return StrategyDecision.close("trailing_exit")
            if time_exit:
                return StrategyDecision.close("time_exit")
            return StrategyDecision.hold()

        if cross_up:
            return StrategyDecision.buy(float(self.params["stake"]), "cross_up")
        return StrategyDecision.hold()


class BreakoutChannelCore(BasePortableStrategy):
    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        lookback = int(self.params["lookback"])
        if len(context.bars) <= lookback:
            return StrategyDecision.hold("warmup")

        lookback_bars = context.bars[-(lookback + 1) : -1]
        prev_highest = max(bar.high for bar in lookback_bars)
        prev_lowest = min(bar.low for bar in lookback_bars)

        if context.position.is_open:
            channel_break = context.bar.close < prev_lowest
            time_exit = _bars_held(context) >= int(self.params["max_hold_bars"])
            risk_exit = _should_exit_by_risk(
                context,
                float(self.params["stop_loss_pct"]),
                float(self.params["take_profit_pct"]),
            )
            if channel_break:
                return StrategyDecision.close("channel_break")
            if risk_exit:
                return StrategyDecision.close("risk_exit")
            if time_exit:
                return StrategyDecision.close("time_exit")
            return StrategyDecision.hold()

        if context.bar.close > prev_highest:
            return StrategyDecision.buy(float(self.params["stake"]), "breakout")
        return StrategyDecision.hold()


class VolumeRallyCore(BasePortableStrategy):
    def __init__(self, params: dict[str, Any]):
        super().__init__(params)
        self._last_exit_bar_index: int | None = None

    def load_state(self, state: dict[str, Any] | None) -> None:
        if not state:
            self._last_exit_bar_index = None
            return
        raw_index = state.get("last_exit_bar_index")
        self._last_exit_bar_index = int(raw_index) if raw_index is not None else None

    def dump_state(self) -> dict[str, Any]:
        return {"last_exit_bar_index": self._last_exit_bar_index}

    def _current_bar_index(self, context: StrategyContext) -> int:
        return len(context.bars) - 1

    def _in_cooldown(self, context: StrategyContext) -> bool:
        cooldown_bars = int(self.params["cooldown_bars"])
        if cooldown_bars <= 0 or self._last_exit_bar_index is None:
            return False
        bars_since_exit = self._current_bar_index(context) - self._last_exit_bar_index
        return bars_since_exit < cooldown_bars

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        closes = _closes(context.bars)
        highs = _highs(context.bars)
        lows = _lows(context.bars)
        volumes = _volumes(context.bars)
        vwap = _session_vwap(context.bars)
        atr = _atr(highs, lows, closes, int(self.params["atr_period"]))
        volume_sma = _sma(volumes, int(self.params["volume_window"]))
        macd_line, signal_line, histogram = _macd(
            closes,
            int(self.params["macd_fast"]),
            int(self.params["macd_slow"]),
            int(self.params["macd_signal"]),
        )
        adx = _adx(highs, lows, closes, int(self.params["adx_period"]))

        if (
            len(closes) < 3
            or np.isnan(vwap[-1])
            or np.isnan(vwap[-2])
            or np.isnan(atr[-1])
            or np.isnan(volume_sma[-1])
            or np.isnan(macd_line[-1])
            or np.isnan(signal_line[-1])
            or np.isnan(histogram[-1])
            or np.isnan(histogram[-2])
            or np.isnan(adx[-1])
        ):
            return StrategyDecision.hold("warmup")

        if context.position.is_open:
            atr_value = float(atr[-1])
            if atr_value <= 0:
                return StrategyDecision.hold("warmup")

            entry_bars = _entry_bars(context)
            highest_close = max((bar.close for bar in entry_bars), default=context.bar.close)
            trailing_stop = highest_close - atr_value * float(self.params["trail_atr_mult"])
            entry_price = float(context.position.entry_price or 0.0)
            fixed_stop = entry_price - atr_value * float(self.params["sl_atr_mult"])
            target_price = entry_price + atr_value * float(self.params["tp_atr_mult"])
            time_exit = _bars_held(context) >= int(self.params["max_hold_bars"])

            if context.bar.close <= trailing_stop:
                self._last_exit_bar_index = self._current_bar_index(context)
                return StrategyDecision.close("trailing_exit")
            if context.bar.close <= fixed_stop:
                self._last_exit_bar_index = self._current_bar_index(context)
                return StrategyDecision.close("atr_stop")
            if context.bar.close >= target_price:
                self._last_exit_bar_index = self._current_bar_index(context)
                return StrategyDecision.close("atr_target")
            if time_exit:
                self._last_exit_bar_index = self._current_bar_index(context)
                return StrategyDecision.close("time_exit")
            return StrategyDecision.hold()

        if self._in_cooldown(context):
            return StrategyDecision.hold("cooldown")

        lookback = int(self.params["breakout_lookback"])
        if len(context.bars) <= lookback:
            return StrategyDecision.hold("warmup")

        prev_highest = float(np.max(highs[-(lookback + 1) : -1]))
        volume_ok = float(volumes[-1]) > float(self.params["volume_spike_mult"]) * float(volume_sma[-1])
        breakout_ok = float(closes[-1]) > prev_highest
        vwap_ok = float(closes[-1]) > float(vwap[-1]) and float(vwap[-1]) > float(vwap[-2])
        expansion_ok = (
            (float(closes[-1]) - float(closes[-2])) > float(self.params["atr_expansion_mult"]) * float(atr[-1])
            or (float(closes[-1]) - float(closes[-3])) > float(self.params["atr_expansion_mult"]) * float(atr[-1])
        )
        macd_ok = (
            float(macd_line[-1]) > float(signal_line[-1])
            and float(histogram[-1]) > 0.0
            and float(histogram[-1]) > float(histogram[-2])
        )
        adx_ok = float(adx[-1]) >= float(self.params["adx_min"])

        if volume_ok and breakout_ok and vwap_ok and expansion_ok and macd_ok and adx_ok:
            return StrategyDecision.buy(float(self.params["stake"]), "confirmed_breakout")
        return StrategyDecision.hold()


class PortableBacktestingStrategy(Strategy):
    strategy_name = ""
    strategy_factory: Any = None
    strategy_params: dict[str, Any] = {}
    strategy_symbol: str | None = None

    def init(self) -> None:
        self.core: StrategyCore = self.strategy_factory(dict(self.strategy_params))
        self.order_log: list[dict[str, Any]] = []
        self.trade_log: list[dict[str, Any]] = []
        self.execution_events: list[ExecutionEvent] = []
        self._bars_history: list[Bar] = []
        self._logged_entry_keys: set[tuple[int, int]] = set()
        self._closed_trade_count = 0
        self._last_entry_reason: str | None = None
        self._last_exit_reason: str | None = None

    def _append_current_bar(self) -> None:
        current_size = len(self.data.Close)
        if len(self._bars_history) == current_size:
            return
        idx = self.data.index[-1]
        self._bars_history.append(
            Bar(
                timestamp=idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx,
                open=float(self.data.Open[-1]),
                high=float(self.data.High[-1]),
                low=float(self.data.Low[-1]),
                close=float(self.data.Close[-1]),
                volume=float(self.data.Volume[-1]),
                is_complete=True,
            )
        )

    def _position_state(self) -> PositionState:
        if not self.trades:
            return PositionState()
        trade = self.trades[0]
        entry_time = trade.entry_time
        current_index = len(self._bars_history) - 1
        bars_held = max(0, current_index - int(trade.entry_bar))
        return PositionState(
            is_open=True,
            size=float(trade.size),
            entry_price=float(trade.entry_price),
            entry_bar_index=int(trade.entry_bar),
            entry_time=entry_time.isoformat() if hasattr(entry_time, "isoformat") else str(entry_time),
            bars_held=bars_held,
        )

    def _record_entry_events(self) -> None:
        for trade in self.trades:
            key = (int(trade.entry_bar), int(trade.size))
            if key in self._logged_entry_keys:
                continue
            self._logged_entry_keys.add(key)
            entry_time = trade.entry_time
            commission = float(getattr(trade, "_commissions", 0.0) or 0.0)
            event = ExecutionEvent(
                event_type="order_filled",
                timestamp=entry_time.isoformat() if hasattr(entry_time, "isoformat") else str(entry_time),
                status="Completed",
                is_buy=bool(trade.is_long),
                size=float(abs(trade.size)),
                price=float(trade.entry_price),
                value=float(abs(trade.size) * trade.entry_price),
                commission=commission,
                reason=self._last_entry_reason,
            )
            self.execution_events.append(event)
            self.order_log.append(
                {
                    "datetime": event.timestamp,
                    "status": event.status,
                    "is_buy": event.is_buy,
                    "size": event.size,
                    "price": event.price,
                    "value": event.value,
                    "commission": event.commission,
                }
            )
            self._last_entry_reason = None

    def _record_closed_trade_events(self) -> None:
        if len(self.closed_trades) <= self._closed_trade_count:
            return
        for trade in self.closed_trades[self._closed_trade_count :]:
            exit_time = trade.exit_time
            commission = float(getattr(trade, "_commissions", 0.0) or 0.0)
            exit_event = ExecutionEvent(
                event_type="order_filled",
                timestamp=exit_time.isoformat() if hasattr(exit_time, "isoformat") else str(exit_time),
                status="Completed",
                is_buy=False,
                size=float(abs(trade.size)),
                price=float(trade.exit_price or 0.0),
                value=float(abs(trade.size) * float(trade.exit_price or 0.0)),
                commission=commission,
                reason=self._last_exit_reason,
            )
            self.execution_events.append(exit_event)
            self.order_log.append(
                {
                    "datetime": exit_event.timestamp,
                    "status": exit_event.status,
                    "is_buy": exit_event.is_buy,
                    "size": exit_event.size,
                    "price": exit_event.price,
                    "value": exit_event.value,
                    "commission": exit_event.commission,
                }
            )
            trade_event = ExecutionEvent(
                event_type="trade_closed",
                timestamp=exit_event.timestamp,
                status="Completed",
                is_buy=False,
                size=float(trade.size),
                price=float(trade.exit_price or 0.0),
                value=float(abs(trade.size) * float(trade.exit_price or 0.0)),
                commission=commission,
                pnl=float(trade.pl + commission),
                pnlcomm=float(trade.pl),
                reason=self._last_exit_reason,
            )
            self.execution_events.append(trade_event)
            self.trade_log.append(
                {
                    "datetime": trade_event.timestamp,
                    "size": trade_event.size,
                    "price": trade_event.price,
                    "value": trade_event.value,
                    "pnl": float(trade_event.pnl or 0.0),
                    "pnlcomm": float(trade_event.pnlcomm or 0.0),
                    "reason": self._last_exit_reason,
                }
            )
            self._last_exit_reason = None
        self._closed_trade_count = len(self.closed_trades)

    def next(self) -> None:
        self._append_current_bar()
        self._record_entry_events()
        self._record_closed_trade_events()
        context = StrategyContext(
            bar=self._bars_history[-1],
            bars=tuple(self._bars_history),
            position=self._position_state(),
            symbol=self.strategy_symbol,
            equity=float(self.equity),
        )
        decision = self.core.on_bar(context)
        if decision.action == "buy" and not self.position:
            self._last_entry_reason = decision.reason
            self.buy(size=float(decision.size or 0.0))
        elif decision.action == "close" and self.position:
            self._last_exit_reason = decision.reason
            self.position.close()


def build_portable_strategy_adapter(
    *,
    strategy_name: str,
    strategy_factory: Any,
    strategy_params: dict[str, Any],
    symbol: str | None,
) -> type[PortableBacktestingStrategy]:
    return type(
        f"{strategy_name.title().replace('_', '')}BacktestingAdapter",
        (PortableBacktestingStrategy,),
        {
            "strategy_name": strategy_name,
            "strategy_factory": strategy_factory,
            "strategy_params": dict(strategy_params),
            "strategy_symbol": symbol,
        },
    )
