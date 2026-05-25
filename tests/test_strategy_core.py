from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.strategies.core import Bar, PositionState, StrategyContext
from app.strategies.implementations import (
    BreakoutChannelCore,
    BuyAndHoldCore,
    BuyOcoAtrTpSlCore,
    BuyOcoAtrTpTrailingCore,
    RsiReversionCore,
    SmaCrossCore,
    VolumeRallyCore,
    _session_vwap,
)
from app.strategies.registry import validate_strategy_params


BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)


def _bars(closes: list[float], highs: list[float] | None = None, lows: list[float] | None = None) -> list[Bar]:
    highs = highs or [c + 1 for c in closes]
    lows = lows or [c - 1 for c in closes]
    return [
        Bar(
            timestamp=BASE_TS + timedelta(days=idx),
            open=close,
            high=highs[idx],
            low=lows[idx],
            close=close,
            volume=1000.0 + idx,
        )
        for idx, close in enumerate(closes)
    ]


def _context(bars: list[Bar], position: PositionState | None = None) -> StrategyContext:
    return StrategyContext(bar=bars[-1], bars=tuple(bars), position=position or PositionState())


def test_sma_cross_core_buy_signal_after_warmup():
    params = validate_strategy_params("sma_cross", {"fast": 2, "slow": 3, "stake": 1})
    core = SmaCrossCore(params)
    decision = core.on_bar(_context(_bars([5, 4, 3, 4, 6])))
    assert decision.action == "buy"
    assert decision.reason == "cross_up"


def test_rsi_reversion_core_exit_signal_when_overbought():
    params = validate_strategy_params("rsi_reversion", {"period": 2, "oversold": 30, "overbought": 60, "stake": 1})
    core = RsiReversionCore(params)
    bars = _bars([10, 8, 9, 12])
    position = PositionState(is_open=True, size=1.0, entry_price=8.0, entry_bar_index=1, entry_time=bars[1].iso_timestamp)
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "close"
    assert decision.reason == "overbought"


def test_buy_and_hold_core_enters_only_once():
    params = validate_strategy_params("buy_and_hold", {"stake": 1})
    core = BuyAndHoldCore(params)
    bars = _bars([100, 101])
    first = core.on_bar(_context(bars))
    second = core.on_bar(_context(bars))
    assert first.action == "buy"
    assert second.action == "hold"


def test_breakout_channel_core_buy_signal():
    params = validate_strategy_params("breakout_channel", {"lookback": 3, "stake": 1})
    core = BreakoutChannelCore(params)
    decision = core.on_bar(_context(_bars([10, 11, 10, 13], highs=[11, 12, 11, 14], lows=[9, 10, 9, 12])))
    assert decision.action == "buy"
    assert decision.reason == "breakout"


def test_buy_oco_atr_tp_sl_core_atr_exit():
    params = validate_strategy_params(
        "buy_oco_atr_tp_sl",
        {"stake": 1, "atr_period": 2, "entry_sma": 2, "sl_atr_mult": 1.0, "tp_atr_mult": 0.5},
    )
    core = BuyOcoAtrTpSlCore(params)
    bars = _bars([100, 101, 103, 106], highs=[101, 102, 104, 107], lows=[99, 100, 102, 105])
    position = PositionState(is_open=True, size=1.0, entry_price=100.0, entry_bar_index=2, entry_time=bars[2].iso_timestamp)
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "close"
    assert decision.reason in {"atr_exit", "time_exit"}


def test_buy_oco_atr_tp_trailing_core_trailing_exit():
    params = validate_strategy_params(
        "buy_oco_atr_tp_trailing",
        {"stake": 1, "atr_period": 2, "entry_sma": 2, "trail_atr_mult": 1.0, "tp_atr_mult": 5.0},
    )
    core = BuyOcoAtrTpTrailingCore(params)
    bars = _bars([100, 102, 110, 107], highs=[101, 103, 111, 108], lows=[99, 101, 109, 106])
    position = PositionState(is_open=True, size=1.0, entry_price=102.0, entry_bar_index=1, entry_time=bars[1].iso_timestamp)
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "close"
    assert decision.reason in {"trailing_exit", "cross_down"}


def _volume_rally_params(**overrides: float | int) -> dict[str, float | int]:
    params = {
        "stake": 1.0,
        "volume_window": 3,
        "volume_spike_mult": 1.5,
        "breakout_lookback": 3,
        "atr_period": 2,
        "atr_expansion_mult": 0.5,
        "macd_fast": 2,
        "macd_slow": 3,
        "macd_signal": 2,
        "adx_period": 2,
        "adx_min": 10.0,
        "sl_atr_mult": 1.0,
        "tp_atr_mult": 2.0,
        "trail_atr_mult": 1.0,
        "max_hold_bars": 3,
    }
    params.update(overrides)
    return validate_strategy_params("volume_rally", params)


def test_volume_rally_core_warmup():
    core = VolumeRallyCore(_volume_rally_params())
    decision = core.on_bar(_context(_bars([10, 11, 12])))
    assert decision.action == "hold"
    assert decision.reason == "warmup"


def test_volume_rally_core_buy_signal_after_confirmed_breakout():
    core = VolumeRallyCore(_volume_rally_params())
    bars = _bars(
        [10, 10.5, 11, 11.4, 11.7, 12.4],
        highs=[10.2, 10.7, 11.1, 11.5, 11.8, 12.6],
        lows=[9.8, 10.2, 10.7, 11.0, 11.3, 11.8],
    )
    bars[-1] = Bar(
        timestamp=bars[-1].timestamp,
        open=11.8,
        high=12.6,
        low=11.8,
        close=12.4,
        volume=3000.0,
    )
    decision = core.on_bar(_context(bars))
    assert decision.action == "buy"
    assert decision.reason == "confirmed_breakout"


def test_volume_rally_core_requires_volume_spike():
    core = VolumeRallyCore(_volume_rally_params())
    bars = _bars(
        [10, 10.5, 11, 11.4, 11.7, 12.4],
        highs=[10.2, 10.7, 11.1, 11.5, 11.8, 12.6],
        lows=[9.8, 10.2, 10.7, 11.0, 11.3, 11.8],
    )
    decision = core.on_bar(_context(bars))
    assert decision.action == "hold"


def test_volume_rally_core_requires_price_above_vwap():
    core = VolumeRallyCore(_volume_rally_params())
    bars = [
        Bar(timestamp=BASE_TS + timedelta(days=0), open=30.0, high=30.5, low=29.5, close=30.0, volume=6000),
        Bar(timestamp=BASE_TS + timedelta(days=1), open=28.0, high=28.5, low=27.5, close=28.0, volume=6000),
        Bar(timestamp=BASE_TS + timedelta(days=2), open=25.0, high=25.5, low=24.5, close=25.0, volume=6000),
        Bar(timestamp=BASE_TS + timedelta(days=3), open=20.0, high=20.2, low=19.6, close=20.0, volume=1000),
        Bar(timestamp=BASE_TS + timedelta(days=4), open=19.8, high=20.0, low=19.5, close=19.9, volume=1000),
        Bar(timestamp=BASE_TS + timedelta(days=5), open=19.9, high=20.6, low=19.8, close=20.5, volume=3000),
    ]
    decision = core.on_bar(_context(bars))
    assert decision.action == "hold"


def test_volume_rally_core_requires_rising_macd_histogram():
    core = VolumeRallyCore(_volume_rally_params())
    bars = _bars(
        [10, 12, 14, 16, 18, 18.2],
        highs=[10.5, 12.5, 14.5, 16.5, 18.5, 18.4],
        lows=[9.5, 11.5, 13.5, 15.5, 17.5, 17.8],
    )
    bars[-1] = Bar(
        timestamp=bars[-1].timestamp,
        open=18.1,
        high=18.4,
        low=17.8,
        close=18.2,
        volume=6000.0,
    )
    decision = core.on_bar(_context(bars))
    assert decision.action == "hold"


def test_volume_rally_core_requires_adx_threshold():
    core = VolumeRallyCore(_volume_rally_params(adx_min=101.0))
    bars = _bars(
        [10, 10.5, 11, 11.4, 11.7, 12.4],
        highs=[10.2, 10.7, 11.1, 11.5, 11.8, 12.6],
        lows=[9.8, 10.2, 10.7, 11.0, 11.3, 11.8],
    )
    bars[-1] = Bar(
        timestamp=bars[-1].timestamp,
        open=11.8,
        high=12.6,
        low=11.8,
        close=12.4,
        volume=3000.0,
    )
    decision = core.on_bar(_context(bars))
    assert decision.action == "hold"


def test_volume_rally_core_exit_on_atr_stop():
    core = VolumeRallyCore(_volume_rally_params(trail_atr_mult=10.0, sl_atr_mult=0.5))
    bars = _bars(
        [10, 10.5, 11, 11.5, 12, 11],
        highs=[10.4, 10.9, 11.4, 11.9, 12.4, 11.3],
        lows=[9.6, 10.1, 10.6, 11.1, 11.6, 10.7],
    )
    position = PositionState(is_open=True, size=1.0, entry_price=12.0, entry_bar_index=4, entry_time=bars[4].iso_timestamp)
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "close"
    assert decision.reason == "atr_stop"


def test_volume_rally_core_exit_on_atr_target():
    core = VolumeRallyCore(_volume_rally_params(trail_atr_mult=10.0, tp_atr_mult=1.0))
    bars = _bars(
        [10, 10.5, 11, 11.5, 12, 14],
        highs=[10.4, 10.9, 11.4, 11.9, 12.4, 14.4],
        lows=[9.6, 10.1, 10.6, 11.1, 11.6, 13.6],
    )
    position = PositionState(is_open=True, size=1.0, entry_price=12.0, entry_bar_index=4, entry_time=bars[4].iso_timestamp)
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "close"
    assert decision.reason == "atr_target"


def test_volume_rally_core_exit_on_trailing_stop():
    core = VolumeRallyCore(_volume_rally_params(sl_atr_mult=10.0, tp_atr_mult=10.0, trail_atr_mult=0.5))
    bars = _bars(
        [10, 10.5, 11, 12, 14, 13.1],
        highs=[10.4, 10.9, 11.4, 12.4, 14.4, 13.4],
        lows=[9.6, 10.1, 10.6, 11.6, 13.6, 12.8],
    )
    position = PositionState(is_open=True, size=1.0, entry_price=11.0, entry_bar_index=2, entry_time=bars[2].iso_timestamp)
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "close"
    assert decision.reason == "trailing_exit"


def test_session_vwap_resets_each_trading_day():
    bars = [
        Bar(timestamp=BASE_TS.replace(hour=10), open=10, high=10.5, low=9.5, close=10.0, volume=1000),
        Bar(timestamp=BASE_TS.replace(hour=11), open=20, high=20.5, low=19.5, close=20.0, volume=1000),
        Bar(timestamp=BASE_TS.replace(day=2, hour=10), open=30, high=30.5, low=29.5, close=30.0, volume=1000),
    ]
    values = _session_vwap(bars)
    assert values[0] == 10.0
    assert values[1] == 15.0
    assert values[2] == 30.0


def test_volume_rally_core_holds_without_vwap_loss_exit():
    core = VolumeRallyCore(
        _volume_rally_params(sl_atr_mult=10.0, trail_atr_mult=10.0, tp_atr_mult=10.0, max_hold_bars=100)
    )
    bars = [
        Bar(timestamp=BASE_TS + timedelta(days=0), open=10, high=10.5, low=9.5, close=10.0, volume=1000),
        Bar(timestamp=BASE_TS + timedelta(days=1), open=11, high=11.5, low=10.5, close=11.0, volume=1000),
        Bar(timestamp=BASE_TS + timedelta(days=2), open=12, high=12.5, low=11.5, close=12.0, volume=1000),
        Bar(timestamp=BASE_TS + timedelta(days=3), open=13, high=13.5, low=12.5, close=13.0, volume=1000),
        Bar(timestamp=BASE_TS + timedelta(days=4), open=14, high=14.5, low=13.5, close=14.0, volume=1000),
        Bar(timestamp=BASE_TS + timedelta(days=5), open=12.2, high=12.4, low=11.8, close=12.0, volume=12000),
    ]
    position = PositionState(is_open=True, size=1.0, entry_price=11.0, entry_bar_index=1, entry_time=bars[1].iso_timestamp)
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "hold"


def test_volume_rally_core_holds_without_macd_rollover_exit():
    core = VolumeRallyCore(
        _volume_rally_params(sl_atr_mult=10.0, trail_atr_mult=10.0, tp_atr_mult=10.0, max_hold_bars=100)
    )
    bars = _bars(
        [10, 11, 12, 13, 14, 13.7],
        highs=[10.4, 11.4, 12.4, 13.4, 14.4, 14.0],
        lows=[9.6, 10.6, 11.6, 12.6, 13.6, 13.5],
    )
    position = PositionState(is_open=True, size=1.0, entry_price=12.0, entry_bar_index=2, entry_time=bars[2].iso_timestamp)
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "hold"


def test_volume_rally_core_exit_on_time():
    core = VolumeRallyCore(_volume_rally_params(max_hold_bars=2, sl_atr_mult=10.0, trail_atr_mult=10.0, tp_atr_mult=10.0))
    bars = _bars(
        [10, 11, 12, 13, 15, 18],
        highs=[10.4, 11.4, 12.4, 13.4, 15.4, 18.4],
        lows=[9.6, 10.6, 11.6, 12.6, 14.6, 17.6],
    )
    position = PositionState(
        is_open=True,
        size=1.0,
        entry_price=12.0,
        entry_bar_index=2,
        entry_time=bars[2].iso_timestamp,
        bars_held=2,
    )
    decision = core.on_bar(_context(bars, position))
    assert decision.action == "close"
    assert decision.reason == "time_exit"


def test_volume_rally_core_cooldown_blocks_reentry():
    core = VolumeRallyCore(
        _volume_rally_params(
            cooldown_bars=5,
            trail_atr_mult=0.5,
            sl_atr_mult=10.0,
            tp_atr_mult=10.0,
        )
    )
    bars = _bars(
        [10, 10.5, 11, 12, 14, 13.1],
        highs=[10.4, 10.9, 11.4, 12.4, 14.4, 13.4],
        lows=[9.6, 10.1, 10.6, 11.6, 13.6, 12.8],
    )
    position = PositionState(
        is_open=True,
        size=1.0,
        entry_price=11.0,
        entry_bar_index=2,
        entry_time=bars[2].iso_timestamp,
    )
    exit_decision = core.on_bar(_context(bars, position))
    assert exit_decision.action == "close"
    assert exit_decision.reason == "trailing_exit"

    breakout_bar = Bar(
        timestamp=BASE_TS + timedelta(days=6),
        open=13.0,
        high=14.6,
        low=12.8,
        close=14.0,
        volume=6000.0,
    )
    extended = bars + [breakout_bar]
    cooldown_decision = core.on_bar(_context(extended))
    assert cooldown_decision.action == "hold"
    assert cooldown_decision.reason == "cooldown"


def test_volume_rally_core_cooldown_zero_allows_immediate_reentry():
    core = VolumeRallyCore(_volume_rally_params(cooldown_bars=0))
    core._last_exit_bar_index = 5
    bars = _bars([10, 11, 12, 13, 14, 15])
    assert core._in_cooldown(_context(bars)) is False


def test_volume_rally_core_persists_cooldown_state():
    core = VolumeRallyCore(_volume_rally_params(cooldown_bars=3))
    core._last_exit_bar_index = 4
    state = core.dump_state()
    restored = VolumeRallyCore(_volume_rally_params(cooldown_bars=3))
    restored.load_state(state)
    assert restored._last_exit_bar_index == 4
