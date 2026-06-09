from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np

from app.strategies.components import ComposableStrategyCore, ExitRuleCore, TriggerCore
from app.strategies.core import Bar, PositionState, StrategyContext, StrategyDecision
from app.strategies.exit_rules import get_exit_rule_spec, validate_exit_rule_params


BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)
US_EASTERN = ZoneInfo("America/New_York")


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
    return StrategyContext(
        bar=bars[-1],
        bars=tuple(bars),
        position=position or PositionState(),
        benchmark_bars=None,
    )


def _open_position(*, bars: list[Bar], entry_bar_index: int, entry_price: float) -> PositionState:
    return PositionState(
        is_open=True,
        size=1.0,
        entry_price=entry_price,
        entry_bar_index=entry_bar_index,
        entry_time=bars[entry_bar_index].iso_timestamp,
    )


def _rth_bars(
    closes: list[float],
    *,
    highs: list[float] | None = None,
    lows: list[float] | None = None,
    volumes: list[float] | None = None,
) -> list[Bar]:
    highs = highs or [c + 0.5 for c in closes]
    lows = lows or [c - 0.5 for c in closes]
    volumes = volumes or [1000.0 + idx * 25 for idx in range(len(closes))]
    return [
        Bar(
            timestamp=datetime(2024, 1, 2, 9, 30, tzinfo=US_EASTERN) + timedelta(minutes=5 * idx),
            open=close - 0.1,
            high=highs[idx],
            low=lows[idx],
            close=close,
            volume=volumes[idx],
        )
        for idx, close in enumerate(closes)
    ]


def test_atr_take_profit_holds_until_threshold_then_closes():
    params = validate_exit_rule_params("atr_take_profit", {"atr_period": 2, "tp_atr_mult": 1.0})
    rule = get_exit_rule_spec("atr_take_profit").factory(params)
    bars = _bars([100, 101, 101.05], highs=[100.1, 101.1, 101.15], lows=[99.9, 100.9, 100.95])
    position = _open_position(bars=bars, entry_bar_index=1, entry_price=101.0)
    assert rule.on_bar(_context(bars, position)).action == "hold"

    bars2 = _bars([100, 101, 105], highs=[100.1, 101.1, 105.1], lows=[99.9, 100.9, 104.9])
    position2 = _open_position(bars=bars2, entry_bar_index=1, entry_price=101.0)
    assert rule.on_bar(_context(bars2, position2)).action == "close"


def test_atr_trailing_stop_ratchets_and_closes_on_retrace():
    params = validate_exit_rule_params("atr_trailing_stop", {"atr_period": 2, "trail_atr_mult": 1.0})
    rule = get_exit_rule_spec("atr_trailing_stop").factory(params)

    bars = _bars([100, 102, 102.6], highs=[100.1, 102.1, 102.7], lows=[99.9, 101.9, 102.5])
    position = _open_position(bars=bars, entry_bar_index=1, entry_price=102.0)
    rule.on_trade_opened(_context(bars[:2], position), StrategyDecision.buy(1.0, "t"))
    assert rule.on_bar(_context(bars, position)).action == "hold"

    bars2 = _bars([100, 102, 102.6, 100], highs=[100.1, 102.1, 102.7, 100.1], lows=[99.9, 101.9, 102.5, 99.9])
    position2 = _open_position(bars=bars2, entry_bar_index=1, entry_price=102.0)
    assert rule.on_bar(_context(bars2, position2)).action == "close"


def test_atr_profit_protect_stop_arms_then_trails_from_peak():
    params = validate_exit_rule_params(
        "atr_profit_protect_stop",
        {"atr_period": 2, "sl_atr_mult": 1.0, "arm_atr_mult": 0.5, "trail_atr_mult": 1.0},
    )
    rule = get_exit_rule_spec("atr_profit_protect_stop").factory(params)

    bars = _bars([100, 102], highs=[100.1, 102.1], lows=[99.9, 101.9])
    position = _open_position(bars=bars, entry_bar_index=1, entry_price=102.0)
    rule.on_trade_opened(_context(bars, position), StrategyDecision.buy(1.0, "t"))

    bars_armed = _bars([100, 102, 102.6], highs=[100.1, 102.1, 102.7], lows=[99.9, 101.9, 102.5])
    position_armed = _open_position(bars=bars_armed, entry_bar_index=1, entry_price=102.0)
    assert rule.on_bar(_context(bars_armed, position_armed)).action == "hold"
    state = rule.dump_state()
    assert state["armed"] is True

    bars_retrace = _bars([100, 102, 102.6, 100], highs=[100.1, 102.1, 102.7, 100.1], lows=[99.9, 101.9, 102.5, 99.9])
    position_retrace = _open_position(bars=bars_retrace, entry_bar_index=1, entry_price=102.0)
    assert rule.on_bar(_context(bars_retrace, position_retrace)).action == "close"


def test_exit_rule_order_is_yaml_order_first_close_wins():
    class DummyTrigger(TriggerCore):
        def on_bar(self, context: StrategyContext) -> StrategyDecision:
            return StrategyDecision.hold()

    bars = _bars([100, 102, 110], highs=[101, 103, 111], lows=[99, 101, 109])
    position = _open_position(bars=bars, entry_bar_index=1, entry_price=102.0)
    context = _context(bars, position)

    tp_params = validate_exit_rule_params("atr_take_profit", {"atr_period": 2, "tp_atr_mult": 0.1})
    tp_rule = get_exit_rule_spec("atr_take_profit").factory(tp_params)

    trail_params = validate_exit_rule_params("atr_trailing_stop", {"atr_period": 2, "trail_atr_mult": 0.1})
    trail_rule = get_exit_rule_spec("atr_trailing_stop").factory(trail_params)
    trail_rule.on_trade_opened(_context(bars[:2], position), StrategyDecision.buy(1.0, "t"))

    core = ComposableStrategyCore(
        trigger_name="dummy",
        trigger=DummyTrigger(),
        exit_rules=[("atr_take_profit", tp_rule), ("atr_trailing_stop", trail_rule)],
    )
    decision = core.on_bar(context)
    assert decision.action == "close"
    assert (decision.reason or "").startswith("exit:atr_take_profit:")


def test_composable_strategy_core_propagates_trim_decisions():
    class DummyTrigger(TriggerCore):
        def on_bar(self, context: StrategyContext) -> StrategyDecision:
            return StrategyDecision.hold()

    class DummyTrimRule(ExitRuleCore):
        def __init__(self) -> None:
            self.trimmed = False

        def on_trade_trimmed(self, context: StrategyContext, decision: StrategyDecision) -> None:
            self.trimmed = True

        def on_bar(self, context: StrategyContext) -> StrategyDecision:
            return StrategyDecision.trim(0.5, "scale_out")

    bars = _bars([100, 101, 102])
    position = _open_position(bars=bars, entry_bar_index=1, entry_price=101.0)
    context = _context(bars, position)

    rule = DummyTrimRule()
    core = ComposableStrategyCore(
        trigger_name="dummy",
        trigger=DummyTrigger(),
        exit_rules=[("trim", rule)],
    )
    decision = core.on_bar(context)
    assert decision.action == "trim"
    assert decision.portion == 0.5
    assert (decision.reason or "").startswith("exit:trim:scale_out")
    assert rule.trimmed is True


def test_vwap_pullback_manage_trims_then_arms_breakeven():
    params = validate_exit_rule_params(
        "vwap_pullback_manage",
        {
            "stop_buffer_pct": 0.001,
            "breakeven_buffer_pct": 0.0,
            "partial_trim_portion": 0.5,
            "time_stop_bars": 100,
            "eod_flatten_minutes": 385,
        },
    )
    rule = get_exit_rule_spec("vwap_pullback_manage").factory(params)

    bars = _rth_bars([99.5, 99.7, 99.8, 99.9, 100.0, 100.1, 100.2, 100.3, 101.0])
    position = _open_position(bars=bars, entry_bar_index=7, entry_price=100.0)
    rule.on_trade_opened(_context(bars[:8], position), StrategyDecision.buy(1.0, "entry"))

    trim_decision = rule.on_bar(_context(bars, position))
    assert trim_decision.action == "trim"
    assert trim_decision.portion == 0.5
    assert trim_decision.reason == "one_r_trim"

    rule.on_trade_trimmed(_context(bars, position), trim_decision)
    retrace_bars = _rth_bars([99.5, 99.7, 99.8, 99.9, 100.0, 100.1, 100.2, 100.3, 101.0, 99.9])
    retrace_position = _open_position(bars=retrace_bars, entry_bar_index=7, entry_price=100.0)
    close_decision = rule.on_bar(_context(retrace_bars, retrace_position))
    assert close_decision.action == "close"
    assert close_decision.reason == "breakeven_exit"


def test_vwap_pullback_manage_exits_on_ema9_vwap_time_and_eod():
    base_params = {
        "stop_buffer_pct": 0.001,
        "breakeven_buffer_pct": 0.0,
        "partial_trim_portion": 0.5,
        "time_stop_bars": 4,
        "eod_flatten_minutes": 385,
    }

    ema_rule = get_exit_rule_spec("vwap_pullback_manage").factory(validate_exit_rule_params("vwap_pullback_manage", base_params))
    ema_bars = _rth_bars(
        [99.8, 99.9, 100.0, 100.05, 100.1, 100.08, 100.06, 100.03, 99.98],
        highs=[100.0, 100.1, 100.2, 100.25, 100.3, 100.28, 100.26, 100.23, 100.18],
        lows=[99.5, 99.6, 99.7, 99.75, 99.8, 99.78, 99.76, 99.73, 99.68],
    )
    ema_position = _open_position(bars=ema_bars, entry_bar_index=0, entry_price=99.8)
    ema_rule.on_trade_opened(_context(ema_bars[:1], ema_position), StrategyDecision.buy(1.0, "entry"))
    ema_decision = ema_rule.on_bar(_context(ema_bars, ema_position))
    assert ema_decision.action == "close"
    assert ema_decision.reason == "ema9_exit"

    time_rule = get_exit_rule_spec("vwap_pullback_manage").factory(validate_exit_rule_params("vwap_pullback_manage", base_params))
    time_bars = _rth_bars([99.8, 99.85, 99.9, 99.95, 100.0, 100.02, 100.03, 100.04, 100.05])
    time_position = _open_position(bars=time_bars, entry_bar_index=0, entry_price=99.8)
    time_rule.on_trade_opened(_context(time_bars[:1], time_position), StrategyDecision.buy(1.0, "entry"))
    time_decision = time_rule.on_bar(_context(time_bars, time_position))
    assert time_decision.action == "close"
    assert time_decision.reason == "time_exit"

    eod_params = {**base_params, "time_stop_bars": 1000}
    eod_rule = get_exit_rule_spec("vwap_pullback_manage").factory(validate_exit_rule_params("vwap_pullback_manage", eod_params))
    eod_bars = [
        Bar(timestamp=datetime(2024, 1, 2, 15, 15, tzinfo=US_EASTERN), open=99.9, high=100.2, low=99.8, close=99.8, volume=1000.0),
        Bar(timestamp=datetime(2024, 1, 2, 15, 20, tzinfo=US_EASTERN), open=99.8, high=100.0, low=99.7, close=99.85, volume=1000.0),
        Bar(timestamp=datetime(2024, 1, 2, 15, 25, tzinfo=US_EASTERN), open=99.85, high=100.1, low=99.75, close=99.9, volume=1000.0),
        Bar(timestamp=datetime(2024, 1, 2, 15, 30, tzinfo=US_EASTERN), open=99.9, high=100.15, low=99.8, close=99.95, volume=1000.0),
        Bar(timestamp=datetime(2024, 1, 2, 15, 35, tzinfo=US_EASTERN), open=99.95, high=100.2, low=99.85, close=100.0, volume=1000.0),
        Bar(timestamp=datetime(2024, 1, 2, 15, 40, tzinfo=US_EASTERN), open=100.0, high=100.22, low=99.88, close=100.02, volume=1000.0),
        Bar(timestamp=datetime(2024, 1, 2, 15, 45, tzinfo=US_EASTERN), open=100.02, high=100.25, low=99.9, close=100.03, volume=1000.0),
        Bar(timestamp=datetime(2024, 1, 2, 15, 50, tzinfo=US_EASTERN), open=100.03, high=100.27, low=99.92, close=100.04, volume=1000.0),
        Bar(timestamp=datetime(2024, 1, 2, 15, 55, tzinfo=US_EASTERN), open=100.04, high=100.3, low=99.95, close=100.05, volume=1000.0),
    ]
    eod_position = PositionState(
        is_open=True,
        size=1.0,
        entry_price=100.0,
        entry_bar_index=0,
        entry_time=eod_bars[0].iso_timestamp,
    )
    eod_rule.on_trade_opened(_context(eod_bars[:1], eod_position), StrategyDecision.buy(1.0, "entry"))
    eod_decision = eod_rule.on_bar(_context(eod_bars, eod_position))
    assert eod_decision.action == "close"
    assert eod_decision.reason == "eod_exit"


def test_vwap_pullback_manage_exits_on_vwap_loss(monkeypatch):
    params = validate_exit_rule_params(
        "vwap_pullback_manage",
        {
            "stop_buffer_pct": 0.001,
            "breakeven_buffer_pct": 0.0,
            "partial_trim_portion": 0.5,
            "time_stop_bars": 1000,
            "eod_flatten_minutes": 385,
        },
    )
    rule = get_exit_rule_spec("vwap_pullback_manage").factory(params)

    bars = _rth_bars([100.0 for _ in range(9)])
    position = _open_position(bars=bars, entry_bar_index=0, entry_price=100.0)
    rule.on_trade_opened(_context(bars[:1], position), StrategyDecision.buy(1.0, "entry"))

    monkeypatch.setattr(
        "app.strategies.exit_rules._ema",
        lambda closes, period: np.asarray([100.0 for _ in range(len(closes) - 1)] + [99.5], dtype=float),
    )
    monkeypatch.setattr(
        "app.strategies.exit_rules._session_vwap",
        lambda bars: np.asarray([100.0 for _ in range(len(bars) - 1)] + [101.0], dtype=float),
    )

    decision = rule.on_bar(_context(bars, position))
    assert decision.action == "close"
    assert decision.reason == "vwap_exit"
