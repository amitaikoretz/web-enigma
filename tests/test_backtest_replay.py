from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pandas as pd

from app.backtests.models import BacktestTradeReplayCapsule
from app.backtests.replay import resolve_trade_replay_target_bar_index


def test_resolve_trade_replay_target_bar_index_uses_first_bar_at_or_after_target(monkeypatch) -> None:
    run = SimpleNamespace(
        run_id="run-1",
        data=SimpleNamespace(type="csv"),
        start_date=datetime(2024, 1, 2).date(),
        end_date=datetime(2024, 1, 3).date(),
    )
    config = SimpleNamespace(
        runs=[run],
        global_config=SimpleNamespace(data_cache=None),
    )
    feed = pd.DataFrame(
        {"Close": [1.0, 2.0, 3.0]},
        index=pd.to_datetime(
            [
                "2024-01-02T09:55:00",
                "2024-01-02T10:00:00",
                "2024-01-02T10:05:00",
            ]
        ),
    )
    capsule = BacktestTradeReplayCapsule.model_validate(
        {
            "backtest_id": "bt-1",
            "run_id": "run-1",
            "run_strategy": "demo",
            "trade_index": 0,
            "target_methods": ["app.strategies.implementations.PortableBacktestingStrategy.next"],
            "break_at": "entry",
            "trade": {
                "datetime": "2024-01-02T10:05:00+00:00",
                "size": 1.0,
                "price": 1.0,
                "value": 1.0,
                "pnl": 0.0,
                "pnlcomm": 0.0,
                "entry_datetime": "2024-01-02T10:00:00+00:00",
            },
            "trade_entry_time": "2024-01-02T10:00:00+00:00",
            "trade_exit_time": "2024-01-02T10:05:00+00:00",
            "config_text": "runs: []",
        }
    )

    monkeypatch.setattr("app.backtests.replay._resolve_run", lambda _config, _run_id: run)
    monkeypatch.setattr("app.backtests.replay._build_run_data_feed", lambda _run, _cache_config: feed)

    resolved = resolve_trade_replay_target_bar_index(config, capsule)

    assert resolved == 1


def test_resolve_trade_replay_target_bar_index_handles_timezone_mismatch(monkeypatch) -> None:
    run = SimpleNamespace(
        run_id="run-1",
        data=SimpleNamespace(type="csv"),
        start_date=datetime(2024, 1, 2).date(),
        end_date=datetime(2024, 1, 3).date(),
    )
    config = SimpleNamespace(
        runs=[run],
        global_config=SimpleNamespace(data_cache=None),
    )
    feed = pd.DataFrame(
        {"Close": [1.0, 2.0]},
        index=pd.to_datetime(
            [
                "2024-01-02T09:55:00+00:00",
                "2024-01-02T10:00:00+00:00",
            ]
        ),
    )
    capsule = BacktestTradeReplayCapsule.model_validate(
        {
            "backtest_id": "bt-1",
            "run_id": "run-1",
            "run_strategy": "demo",
            "trade_index": 0,
            "target_methods": ["app.strategies.components.ComposableStrategyCore.on_bar"],
            "break_at": "entry",
            "trade": {
                "datetime": "2024-01-02T10:00:00+00:00",
                "size": 1.0,
                "price": 1.0,
                "value": 1.0,
                "pnl": 0.0,
                "pnlcomm": 0.0,
                "entry_datetime": "2024-01-02T10:00:00+00:00",
            },
            "trade_entry_time": "2024-01-02T10:00:00+00:00",
            "trade_exit_time": "2024-01-02T10:00:00+00:00",
            "config_text": "runs: []",
        }
    )

    monkeypatch.setattr("app.backtests.replay._resolve_run", lambda _config, _run_id: run)
    monkeypatch.setattr("app.backtests.replay._build_run_data_feed", lambda _run, _cache_config: feed)

    resolved = resolve_trade_replay_target_bar_index(config, capsule)

    assert resolved == 1
