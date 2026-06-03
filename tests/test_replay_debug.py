from __future__ import annotations

from datetime import UTC, datetime

import builtins

from app.replay_debug import (
    ReplayDebugTarget,
    clear_trade_replay_debug_target,
    install_trade_replay_debug_target,
    maybe_break_for_trade_replay,
)


def test_trade_replay_breaks_for_equivalent_timestamp_formats(monkeypatch) -> None:
    calls: list[None] = []

    def fake_breakpoint() -> None:
        calls.append(None)

    monkeypatch.setattr(builtins, 'breakpoint', fake_breakpoint)
    install_trade_replay_debug_target(
        ReplayDebugTarget(
            target_bar_time=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
            target_methods=('app.strategies.implementations.PortableBacktestingStrategy.next',),
        )
    )

    maybe_break_for_trade_replay(
        'app.strategies.implementations.PortableBacktestingStrategy.next',
        timestamp='2024-01-02T10:00:00.000000+00:00',
    )

    assert len(calls) == 1

    clear_trade_replay_debug_target()


def test_trade_replay_prefers_bar_index_when_available(monkeypatch) -> None:
    calls: list[None] = []

    def fake_breakpoint() -> None:
        calls.append(None)

    monkeypatch.setattr(builtins, 'breakpoint', fake_breakpoint)
    install_trade_replay_debug_target(
        ReplayDebugTarget(
            target_bar_index=7,
            target_bar_time=None,
            target_methods=('app.strategies.implementations.PortableBacktestingStrategy.next',),
        )
    )

    maybe_break_for_trade_replay(
        'app.strategies.implementations.PortableBacktestingStrategy.next',
        bar_index=7,
        timestamp='2024-01-02T10:00:00.000000+00:00',
    )

    assert len(calls) == 1

    clear_trade_replay_debug_target()


def test_trade_replay_breaks_when_bar_index_has_moved_past_target(monkeypatch) -> None:
    calls: list[None] = []

    def fake_breakpoint() -> None:
        calls.append(None)

    monkeypatch.setattr(builtins, "breakpoint", fake_breakpoint)
    install_trade_replay_debug_target(
        ReplayDebugTarget(
            target_bar_index=7,
            target_bar_time=None,
            target_methods=("app.strategies.implementations.PortableBacktestingStrategy.next",),
        )
    )

    maybe_break_for_trade_replay(
        "app.strategies.implementations.PortableBacktestingStrategy.next",
        bar_index=8,
        timestamp="2024-01-02T10:00:00.000000+00:00",
    )

    assert len(calls) == 1

    clear_trade_replay_debug_target()


def test_trade_replay_breaks_on_first_bar_at_or_after_target(monkeypatch) -> None:
    calls: list[None] = []

    def fake_breakpoint() -> None:
        calls.append(None)

    monkeypatch.setattr(builtins, "breakpoint", fake_breakpoint)
    install_trade_replay_debug_target(
        ReplayDebugTarget(
            target_bar_time=datetime(2024, 1, 2, 10, 0, 0, tzinfo=UTC),
            target_methods=("app.strategies.components.ComposableStrategyCore.on_bar",),
        )
    )

    maybe_break_for_trade_replay(
        "app.strategies.components.ComposableStrategyCore.on_bar",
        timestamp="2024-01-02T10:05:00.000000+00:00",
    )

    assert len(calls) == 1

    clear_trade_replay_debug_target()
