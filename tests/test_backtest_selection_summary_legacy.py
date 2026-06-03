from __future__ import annotations

from datetime import date

from app.backtests.models import BacktestSelectionSummary


def test_backtest_selection_summary_accepts_legacy_strategies_list():
    summary = BacktestSelectionSummary.model_validate(
        {
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 1, 2),
            "resolution": "1d",
            "feed": "iex",
            "symbols": ["AAPL"],
            "strategies": ["sma_cross", "volume_rally"],
        }
    )
    assert summary.triggers == ["sma_cross", "volume_rally"]
    assert summary.exit_rules == ["unknown"]


def test_backtest_selection_summary_accepts_legacy_strategy_string():
    summary = BacktestSelectionSummary.model_validate(
        {
            "start_date": date(2024, 1, 1),
            "end_date": date(2024, 1, 2),
            "resolution": "1d",
            "feed": "iex",
            "symbols": ["AAPL"],
            "strategy": "sma_cross",
        }
    )
    assert summary.triggers == ["sma_cross"]
    assert summary.exit_rules == ["unknown"]

