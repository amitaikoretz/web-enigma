from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from backtesting import Strategy

from app.strategies.auditor_logging import log_auditor_rejection
from app.strategies.candidates import CandidateEvent, record_candidate
from app.strategies.core import Bar, ExecutionEvent, PositionState, StrategyContext, StrategyCore, StrategyDecision
from app.strategies.entry_plans import atr_entry_intent, fixed_pct_entry_intent
from app.strategies.regime import RegimeClassifier, regime_params_from_strategy


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


SESSION_CLOSE_REASON = "session_close"
US_EASTERN = ZoneInfo("America/New_York")
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)


def _to_eastern(timestamp: datetime | Any) -> datetime:
    if hasattr(timestamp, "to_pydatetime"):
        timestamp = timestamp.to_pydatetime()
    if not isinstance(timestamp, datetime):
        raise TypeError(f"Expected datetime, got {type(timestamp)!r}")
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=ZoneInfo("UTC"))
    return timestamp.astimezone(US_EASTERN)


def _minutes_since_rth_open(bar: Bar) -> int | None:
    eastern = _to_eastern(bar.timestamp)
    session_open = datetime.combine(eastern.date(), RTH_OPEN, tzinfo=US_EASTERN)
    session_close = datetime.combine(eastern.date(), RTH_CLOSE, tzinfo=US_EASTERN)
    if eastern < session_open or eastern >= session_close:
        return None
    return int((eastern - session_open).total_seconds() // 60)


def _in_session_window(bar: Bar, start_minutes: int, end_minutes: int) -> bool:
    if start_minutes <= 0 and end_minutes <= 0:
        return True
    minutes_since_open = _minutes_since_rth_open(bar)
    if minutes_since_open is None:
        return False
    if start_minutes > 0 and minutes_since_open < start_minutes:
        return False
    if end_minutes > 0 and minutes_since_open > end_minutes:
        return False
    return True


def _close_strength(bar: Bar) -> float:
    bar_range = float(bar.high) - float(bar.low)
    if bar_range <= 0:
        return 1.0
    return (float(bar.close) - float(bar.low)) / bar_range


def _bar_session_date(timestamp: datetime | Any) -> date:
    if hasattr(timestamp, "to_pydatetime"):
        timestamp = timestamp.to_pydatetime()
    if isinstance(timestamp, datetime):
        return timestamp.date()
    return date.fromisoformat(str(timestamp)[:10])


def _is_last_bar_of_session(session_dates: Sequence[date], bar_index: int) -> bool:
    if bar_index >= len(session_dates) - 1:
        return True
    return session_dates[bar_index] != session_dates[bar_index + 1]


def _is_new_session(session_dates: Sequence[date], bar_index: int) -> bool:
    return bar_index == 0 or session_dates[bar_index] != session_dates[bar_index - 1]


def _is_only_bar_of_session(session_dates: Sequence[date], bar_index: int) -> bool:
    return _is_new_session(session_dates, bar_index) and _is_last_bar_of_session(session_dates, bar_index)


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


def _volume_rally_entry_signal(
    *,
    volume_ok: bool,
    breakout_ok: bool,
    vwap_ok: bool,
    expansion_ok: bool,
    macd_ok: bool,
    adx_ok: bool,
    min_confirmations: int,
) -> bool:
    if not (volume_ok and breakout_ok):
        return False
    optional_passed = sum((vwap_ok, expansion_ok, macd_ok, adx_ok))
    optional_required = min_confirmations - 2
    return optional_passed >= optional_required


def _benchmark_regime_ok(context: StrategyContext, params: dict[str, Any]) -> bool:
    benchmark_symbol = str(params.get("benchmark_symbol", "")).strip()
    if not benchmark_symbol:
        return True
    benchmark_bars = context.benchmark_bars
    if not benchmark_bars:
        return False

    closes = _closes(benchmark_bars)
    highs = _highs(benchmark_bars)
    lows = _lows(benchmark_bars)
    sma_period = int(params["benchmark_sma_period"])
    adx_period = int(params["benchmark_adx_period"])
    adx_min = float(params["benchmark_adx_min"])
    require_above_sma = bool(params["benchmark_require_above_sma"])

    sma = _sma(closes, sma_period)
    adx = _adx(highs, lows, closes, adx_period)
    if require_above_sma and np.isnan(sma[-1]):
        return False

    above_sma = require_above_sma and float(closes[-1]) > float(sma[-1])
    adx_ok = adx_min > 0 and not np.isnan(adx[-1]) and float(adx[-1]) >= adx_min

    if require_above_sma and adx_min > 0:
        return above_sma or adx_ok
    if require_above_sma:
        return above_sma
    if adx_min > 0:
        return adx_ok
    return True


def _bars_from_dataframe(feed: Any) -> list[Bar]:
    bars: list[Bar] = []
    for idx, row in feed.iterrows():
        timestamp = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
        bars.append(
            Bar(
                timestamp=timestamp,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                volume=float(row["Volume"]),
                is_complete=True,
            )
        )
    return bars


def _benchmark_bars_as_of(current_bar: Bar, all_benchmark_bars: Sequence[Bar]) -> tuple[Bar, ...]:
    current_ts = current_bar.timestamp
    return tuple(bar for bar in all_benchmark_bars if bar.timestamp <= current_ts)


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
            entry_intent = fixed_pct_entry_intent(
                context,
                self.params,
                signal_score=1.0,
                signal_reason="breakout",
            )
            return StrategyDecision.buy(
                float(self.params["stake"]),
                "breakout",
                entry_intent=entry_intent,
            )
        return StrategyDecision.hold()


class VolumeRallyCore(BasePortableStrategy):
    def __init__(self, params: dict[str, Any]):
        super().__init__(params)
        self._regime = RegimeClassifier(regime_params_from_strategy(params))
        self._last_exit_bar_index: int | None = None
        self._session_trade_date: date | None = None
        self._session_trades_count = 0
        self._breakeven_armed = False
        self._entry_atr: float | None = None
        self._last_entry_regime: str | None = None

    def entry_regime_label(self) -> str | None:
        return self._last_entry_regime

    def load_state(self, state: dict[str, Any] | None) -> None:
        if not state:
            self._last_exit_bar_index = None
            self._session_trade_date = None
            self._session_trades_count = 0
            self._breakeven_armed = False
            self._entry_atr = None
            self._last_entry_regime = None
            self._regime.load_state(None)
            return
        raw_index = state.get("last_exit_bar_index")
        self._last_exit_bar_index = int(raw_index) if raw_index is not None else None
        raw_session_date = state.get("session_trade_date")
        self._session_trade_date = date.fromisoformat(raw_session_date) if raw_session_date else None
        self._session_trades_count = int(state.get("session_trades_count", 0))
        self._breakeven_armed = bool(state.get("breakeven_armed", False))
        raw_entry_atr = state.get("entry_atr")
        self._entry_atr = float(raw_entry_atr) if raw_entry_atr is not None else None
        self._last_entry_regime = state.get("last_entry_regime")
        self._regime.load_state(state.get("regime"))

    def dump_state(self) -> dict[str, Any]:
        return {
            "last_exit_bar_index": self._last_exit_bar_index,
            "session_trade_date": self._session_trade_date.isoformat() if self._session_trade_date else None,
            "session_trades_count": self._session_trades_count,
            "breakeven_armed": self._breakeven_armed,
            "entry_atr": self._entry_atr,
            "last_entry_regime": self._last_entry_regime,
            "regime": self._regime.dump_state(),
        }

    def _current_bar_index(self, context: StrategyContext) -> int:
        return len(context.bars) - 1

    def _sync_session_state(self, context: StrategyContext) -> None:
        session_date = _bar_session_date(context.bar.timestamp)
        if self._session_trade_date is None:
            self._session_trade_date = session_date
        elif self._session_trade_date != session_date:
            self._session_trade_date = session_date
            self._session_trades_count = 0

    def _mark_exit(self, context: StrategyContext) -> None:
        self._last_exit_bar_index = self._current_bar_index(context)
        self._session_trades_count += 1
        self._breakeven_armed = False
        self._entry_atr = None

    def _in_cooldown(self, context: StrategyContext) -> bool:
        cooldown_bars = int(self.params["cooldown_bars"])
        if cooldown_bars <= 0 or self._last_exit_bar_index is None:
            return False
        bars_since_exit = self._current_bar_index(context) - self._last_exit_bar_index
        return bars_since_exit < cooldown_bars

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
        self._sync_session_state(context)
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

        regime = self._regime.update(context.bars)

        if context.position.is_open:
            if regime.label == "high_vol":
                self._mark_exit(context)
                return StrategyDecision.close("regime_high_vol")
            atr_value = self._position_atr(context, atr)
            if atr_value <= 0:
                return StrategyDecision.hold("warmup")

            entry_price = float(context.position.entry_price or 0.0)
            stale_bars = int(self.params["stale_bars"])
            if stale_bars > 0 and _bars_held(context) >= stale_bars:
                min_progress = float(self.params["min_progress_atr"]) * atr_value
                if context.bar.close - entry_price < min_progress:
                    self._mark_exit(context)
                    return StrategyDecision.close("stale_exit")

            self._maybe_arm_breakeven(context, atr_value)

            entry_bars = _entry_bars(context)
            highest_close = max((bar.close for bar in entry_bars), default=context.bar.close)
            trailing_stop = highest_close - atr_value * float(self.params["trail_atr_mult"])
            effective_stop = self._effective_stop(entry_price, atr_value)
            target_price = entry_price + atr_value * float(self.params["tp_atr_mult"])
            time_exit = _bars_held(context) >= int(self.params["max_hold_bars"])

            if context.bar.close <= trailing_stop:
                self._mark_exit(context)
                return StrategyDecision.close("trailing_exit")
            if context.bar.close <= effective_stop:
                self._mark_exit(context)
                return StrategyDecision.close("atr_stop")
            if context.bar.close >= target_price:
                self._mark_exit(context)
                return StrategyDecision.close("atr_target")
            if time_exit:
                self._mark_exit(context)
                return StrategyDecision.close("time_exit")
            return StrategyDecision.hold()

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
        signal_components = {
            "volume_ok": volume_ok,
            "breakout_ok": breakout_ok,
            "vwap_ok": vwap_ok,
            "expansion_ok": expansion_ok,
            "macd_ok": macd_ok,
            "adx_ok": adx_ok,
        }
        signal_ok = _volume_rally_entry_signal(
            volume_ok=volume_ok,
            breakout_ok=breakout_ok,
            vwap_ok=vwap_ok,
            expansion_ok=expansion_ok,
            macd_ok=macd_ok,
            adx_ok=adx_ok,
            min_confirmations=int(self.params["min_confirmations"]),
        )

        core_entry_trigger = volume_ok and breakout_ok
        confirmations = sum(1 for value in signal_components.values() if value)
        entry_intent = None
        if core_entry_trigger:
            initial_sl_mult = float(self.params["initial_sl_atr_mult"])
            sl_mult = initial_sl_mult if initial_sl_mult > 0 else float(self.params["sl_atr_mult"])
            entry_intent = atr_entry_intent(
                float(context.bar.close),
                float(atr[-1]),
                sl_mult=sl_mult,
                tp_mult=float(self.params["tp_atr_mult"]),
                horizon_bars=int(self.params["max_hold_bars"]),
                signal_score=confirmations / len(signal_components),
                signal_reason="volume_rally",
                metadata=signal_components,
            )

        if self._in_cooldown(context):
            return StrategyDecision.hold(
                "cooldown",
                auditor_rejection=core_entry_trigger,
                entry_intent=entry_intent,
            )

        session_start = int(self.params["session_start_minutes"])
        session_end = int(self.params["session_end_minutes"])
        if core_entry_trigger and not _in_session_window(context.bar, session_start, session_end):
            return StrategyDecision.hold("session_window", auditor_rejection=True, entry_intent=entry_intent)

        max_trades = int(self.params["max_trades_per_session"])
        if max_trades > 0 and self._session_trades_count >= max_trades:
            return StrategyDecision.hold(
                "session_trade_cap",
                auditor_rejection=core_entry_trigger,
                entry_intent=entry_intent,
            )

        if not core_entry_trigger:
            return StrategyDecision.hold()

        if not signal_ok:
            return StrategyDecision.hold(
                "insufficient_confirmations",
                auditor_rejection=True,
                entry_intent=entry_intent,
            )

        if regime.label == "ranging":
            return StrategyDecision.hold("regime_ranging", auditor_rejection=True, entry_intent=entry_intent)
        if regime.label == "high_vol":
            return StrategyDecision.hold("regime_high_vol", auditor_rejection=True, entry_intent=entry_intent)

        if not _benchmark_regime_ok(context, self.params):
            reason = "benchmark_regime" if context.benchmark_bars else "benchmark_warmup"
            return StrategyDecision.hold(reason, auditor_rejection=True, entry_intent=entry_intent)

        min_close_strength = float(self.params["min_close_strength"])
        if min_close_strength > 0 and _close_strength(context.bar) < min_close_strength:
            return StrategyDecision.hold("weak_close", auditor_rejection=True, entry_intent=entry_intent)

        self._entry_atr = float(atr[-1])
        self._breakeven_armed = False
        self._last_entry_regime = regime.label
        return StrategyDecision.buy(
            float(self.params["stake"]),
            "confirmed_breakout",
            entry_intent=entry_intent,
        )


class PortableBacktestingStrategy(Strategy):
    strategy_name = ""
    strategy_factory: Any = None
    strategy_params: dict[str, Any] = {}
    strategy_symbol: str | None = None
    benchmark_feed: Any = None
    include_candidate_log = False
    fill_model = "close"
    _bar_progress_callback: Callable[[int], None] | None = None

    def init(self) -> None:
        self.core: StrategyCore = self.strategy_factory(dict(self.strategy_params))
        self.order_log: list[dict[str, Any]] = []
        self.trade_log: list[dict[str, Any]] = []
        self.execution_events: list[ExecutionEvent] = []
        self.candidate_log: list[CandidateEvent] = []
        self._bars_history: list[Bar] = []
        self._all_benchmark_bars: list[Bar] = _bars_from_dataframe(self.benchmark_feed) if self.benchmark_feed is not None else []
        self._session_dates = [_bar_session_date(ts) for ts in self.data.index]
        self._logged_entry_keys: set[tuple[int, int]] = set()
        self._closed_trade_count = 0
        self._last_entry_reason: str | None = None
        self._last_entry_regime: str | None = None
        self._last_exit_reason: str | None = None
        self.rejection_log: list[dict[str, Any]] = []

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
                    "regime_label": self._last_entry_regime,
                }
            )
            self._last_exit_reason = None
            self._last_entry_regime = None
        self._closed_trade_count = len(self.closed_trades)

    def _current_data_index(self) -> int:
        return len(self.data.Close) - 1

    def _enforce_flat_at_session_open(self, data_index: int) -> None:
        if data_index == 0 or not _is_new_session(self._session_dates, data_index):
            return
        self.orders.cancel()
        if self.position:
            self._close_open_position_for_session()

    def _enforce_flat_by_session_close(self, data_index: int) -> None:
        if not _is_last_bar_of_session(self._session_dates, data_index):
            return
        if not _is_only_bar_of_session(self._session_dates, data_index):
            self.orders.cancel()
        if self.position:
            self._close_open_position_for_session()

    def _close_open_position_for_session(self) -> None:
        if not self.position:
            return
        self._last_exit_reason = SESSION_CLOSE_REASON
        self.position.close()

    def next(self) -> None:
        self._append_current_bar()
        data_index = self._current_data_index()
        self._enforce_flat_at_session_open(data_index)

        self._record_entry_events()
        self._record_closed_trade_events()
        current_bar = self._bars_history[-1]
        benchmark_bars = (
            _benchmark_bars_as_of(current_bar, self._all_benchmark_bars) if self._all_benchmark_bars else None
        )
        context = StrategyContext(
            bar=current_bar,
            bars=tuple(self._bars_history),
            position=self._position_state(),
            symbol=self.strategy_symbol,
            equity=float(self.equity),
            benchmark_bars=benchmark_bars,
        )
        decision = self.core.on_bar(context)
        entry_type = "CLOSE" if self.fill_model == "close" else "NEXT_OPEN"
        record_candidate(
            self.candidate_log,
            decision,
            enabled=self.include_candidate_log,
            strategy_id=self.strategy_name,
            symbol=self.strategy_symbol or "UNKNOWN",
            timestamp=context.bar.iso_timestamp,
            entry_type=entry_type,
        )
        if decision.action == "hold" and decision.auditor_rejection:
            rejection = {
                "datetime": context.bar.iso_timestamp,
                "symbol": self.strategy_symbol,
                "reason": decision.reason,
            }
            self.rejection_log.append(rejection)
            log_auditor_rejection(
                symbol=self.strategy_symbol,
                timestamp=context.bar.iso_timestamp,
                reason=decision.reason,
            )
        if decision.action == "buy" and not self.position:
            self._last_entry_reason = decision.reason
            entry_regime = getattr(self.core, "entry_regime_label", None)
            self._last_entry_regime = entry_regime() if callable(entry_regime) else None
            self.buy(size=float(decision.size or 0.0))
        elif decision.action == "close" and self.position:
            self._last_exit_reason = decision.reason
            self.position.close()

        self._enforce_flat_by_session_close(data_index)

        self._record_entry_events()
        self._record_closed_trade_events()

        callback = self.__class__.__dict__.get("_bar_progress_callback")
        if callback is not None:
            callback(len(self._bars_history))


def build_portable_strategy_adapter(
    *,
    strategy_name: str,
    strategy_factory: Any,
    strategy_params: dict[str, Any],
    symbol: str | None,
    benchmark_feed: Any = None,
    include_candidate_log: bool = False,
    fill_model: str = "close",
    bar_progress_callback: Callable[[int], None] | None = None,
) -> type[PortableBacktestingStrategy]:
    attrs: dict[str, Any] = {
        "strategy_name": strategy_name,
        "strategy_factory": strategy_factory,
        "strategy_params": dict(strategy_params),
        "strategy_symbol": symbol,
        "benchmark_feed": benchmark_feed,
        "include_candidate_log": include_candidate_log,
        "fill_model": fill_model,
    }
    if bar_progress_callback is not None:
        attrs["_bar_progress_callback"] = bar_progress_callback
    return type(
        f"{strategy_name.title().replace('_', '')}BacktestingAdapter",
        (PortableBacktestingStrategy,),
        attrs,
    )
