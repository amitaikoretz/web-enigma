from pathlib import Path

import pytest

from app.config.models import BacktestConfig


def _base_run():
    return {
        "run_id": "r1",
        "start_date": "2024-01-01",
        "end_date": "2024-01-19",
        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
        "strategy": "sma_cross",
        "strategy_params": {"fast": 3, "slow": 5, "stake": 1},
    }


def test_valid_config():
    config = {"runs": [_base_run()]}
    parsed = BacktestConfig.model_validate(config)
    assert parsed.runs[0].strategy == "sma_cross"


def test_invalid_date_range():
    run = _base_run()
    run["start_date"] = "2024-01-20"
    run["end_date"] = "2024-01-10"
    with pytest.raises(Exception):
        BacktestConfig.model_validate({"runs": [run]})


def test_invalid_strategy_name():
    run = _base_run()
    run["strategy"] = "not_real"
    with pytest.raises(Exception):
        BacktestConfig.model_validate({"runs": [run]})


def test_invalid_strategy_params():
    run = _base_run()
    run["strategy_params"] = {"fast": -1, "slow": 5}
    with pytest.raises(Exception):
        BacktestConfig.model_validate({"runs": [run]})


def test_csv_path_present_in_example():
    assert Path("examples/data/sample_daily.csv").exists()


def test_valid_config_with_multiple_strategies():
    run = _base_run()
    run.pop("strategy")
    run.pop("strategy_params")
    run["strategies"] = [
        {"name": "sma_cross", "params": {"fast": 3, "slow": 5, "stake": 1}},
        {"name": "rsi_reversion", "params": {"period": 7, "oversold": 30, "overbought": 60, "stake": 1}},
    ]
    parsed = BacktestConfig.model_validate({"runs": [run]})
    assert parsed.runs[0].strategies is not None
    assert len(parsed.runs[0].strategies) == 2


def test_invalid_config_without_strategy_or_strategies():
    run = _base_run()
    run.pop("strategy")
    run.pop("strategy_params")
    with pytest.raises(Exception):
        BacktestConfig.model_validate({"runs": [run]})
