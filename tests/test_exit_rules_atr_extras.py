from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.strategies.components import ComposableStrategyCore, TriggerCore
from app.strategies.core import Bar, PositionState, StrategyContext, StrategyDecision
from app.strategies.exit_rules import get_exit_rule_spec, validate_exit_rule_params


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
