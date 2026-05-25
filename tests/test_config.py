from pathlib import Path

import pytest

from app.config.models import BacktestConfig, LiveTradingConfig


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


def test_valid_backtest_fill_model():
    run = _base_run()
    run["execution"] = {"fill_model": "next_bar"}
    parsed = BacktestConfig.model_validate({"runs": [run]})
    assert parsed.runs[0].execution.fill_model == "next_bar"


def test_valid_alpaca_trading_config():
    config = {
        "runs": [
            {
                "run_id": "live_r1",
                "symbol": "AAPL",
                "interval": "1m",
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
            }
        ]
    }
    from app.config.models import AlpacaTradingConfig

    parsed = AlpacaTradingConfig.model_validate(config)
    assert parsed.runs[0].symbol == "AAPL"


def test_valid_live_trading_config():
    config = {
        "global_config": {
            "controller": {"shard_count": 3},
            "worker": {"shard_id": 1},
        },
        "contracts": [
            {
                "contract_id": "aa0d74d7-7a8d-4fe4-a20f-b5d30e935001",
                "symbol": "AAPL",
                "interval": "1m",
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
            }
        ],
    }
    parsed = LiveTradingConfig.model_validate(config)
    assert parsed.global_config.controller.scale_up_replicas == 3
    assert parsed.contracts[0].symbol == "AAPL"


def test_live_trading_config_rejects_duplicate_contract_ids():
    config = {
        "contracts": [
            {
                "contract_id": "aa0d74d7-7a8d-4fe4-a20f-b5d30e935001",
                "symbol": "AAPL",
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
            },
            {
                "contract_id": "aa0d74d7-7a8d-4fe4-a20f-b5d30e935001",
                "symbol": "MSFT",
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
            },
        ]
    }
    with pytest.raises(Exception):
        LiveTradingConfig.model_validate(config)


def test_live_trading_config_rejects_invalid_redis_timing():
    config = {
        "global_config": {
            "redis": {
                "heartbeat_interval_seconds": 30,
                "lease_ttl_seconds": 20,
            }
        }
    }
    with pytest.raises(Exception):
        LiveTradingConfig.model_validate(config)
