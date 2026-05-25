from __future__ import annotations

from app.engine.metrics import (
    build_trade_distribution,
    compute_filter_diagnostics,
    compute_trade_diagnostics,
    duration_to_minutes,
)
from app.output.models import OrderRecord, RejectionRecord, TradeRecord


def test_duration_to_minutes_parses_timedelta_string():
    assert duration_to_minutes("0 days 00:04:00") == 4.0


def test_compute_trade_diagnostics_basic():
    trades = [
        TradeRecord(
            datetime="2026-05-06T15:00:00",
            size=10.0,
            price=100.0,
            value=1000.0,
            pnl=12.0,
            pnlcomm=10.0,
            reason="atr_target",
            hold_minutes=45.0,
        ),
        TradeRecord(
            datetime="2026-05-07T15:00:00",
            size=10.0,
            price=100.0,
            value=1000.0,
            pnl=-8.0,
            pnlcomm=-10.0,
            reason="trailing_exit",
            hold_minutes=4.0,
        ),
    ]
    orders = [
        OrderRecord(status="Completed", is_buy=True, size=10, price=100, value=1000, commission=1.0),
        OrderRecord(status="Completed", is_buy=False, size=10, price=100, value=1000, commission=1.0),
    ]
    diagnostics = compute_trade_diagnostics(trades, orders, start_value=10000.0, end_value=10000.0)
    assert diagnostics.net_pnl == 0.0
    assert diagnostics.gross_pnl == 4.0
    assert diagnostics.total_commission == 2.0
    assert diagnostics.profit_factor == 1.0
    assert diagnostics.win_rate_pct == 50.0
    assert diagnostics.exit_reason_counts["atr_target"] == 1
    assert diagnostics.exit_reason_pnl["trailing_exit"] == -10.0
    assert diagnostics.distributions is not None
    assert diagnostics.distributions.hold_time_bins[0].count == 1


def test_build_trade_distribution_uses_fixed_hold_bins():
    trades = [
        TradeRecord(size=1, price=1, value=1, pnl=1, pnlcomm=1, hold_minutes=3),
        TradeRecord(size=1, price=1, value=1, pnl=1, pnlcomm=1, hold_minutes=10),
    ]
    distribution = build_trade_distribution(trades)
    assert distribution.hold_time_bins[0].count == 1
    assert distribution.hold_time_bins[1].count == 1


def test_compute_filter_diagnostics_counts_rejections():
    rejections = [
        RejectionRecord(reason="session_window"),
        RejectionRecord(reason="session_window"),
        RejectionRecord(reason="weak_close"),
    ]
    diagnostics = compute_filter_diagnostics(rejections, total_trades=2)
    assert diagnostics.total_rejections == 3
    assert diagnostics.rejection_counts["session_window"] == 2
    assert diagnostics.signal_to_trade_pct == 40.0
