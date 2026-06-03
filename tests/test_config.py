from pathlib import Path

import pytest

from app.config.models import BacktestConfig, LiveTradingConfig


def _base_run():
    return {
        "run_id": "r1",
        "start_date": "2024-01-01",
        "end_date": "2024-01-19",
        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
        "trigger": {"name": "sma_cross", "params": {"fast": 3, "slow": 5, "stake": 1}},
        "exit_rules": {
            "rules": [
                {"name": "sma_cross_down", "params": {"fast": 3, "slow": 5}},
                {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                {"name": "max_hold_bars", "params": {"max_hold_bars": 24}},
            ]
        },
    }


def test_valid_config():
    config = {"runs": [_base_run()]}
    parsed = BacktestConfig.model_validate(config)
    assert parsed.runs[0].trigger is not None
    assert parsed.runs[0].trigger.name == "sma_cross"


def test_invalid_date_range():
    run = _base_run()
    run["start_date"] = "2024-01-20"
    run["end_date"] = "2024-01-10"
    with pytest.raises(Exception):
        BacktestConfig.model_validate({"runs": [run]})


def test_invalid_strategy_name():
    run = _base_run()
    run["trigger"]["name"] = "not_real"
    with pytest.raises(Exception):
        BacktestConfig.model_validate({"runs": [run]})


def test_invalid_strategy_params():
    run = _base_run()
    run["trigger"]["params"] = {"fast": -1, "slow": 5}
    with pytest.raises(Exception):
        BacktestConfig.model_validate({"runs": [run]})


def test_fixed_pct_oco_rejects_legacy_pct_params():
    run = _base_run()
    run["exit_rules"]["rules"][1]["params"] = {"stop_loss_pct": 0.02, "take_profit_pct": 0.04}
    with pytest.raises(Exception, match=r"fixed_pct_oco now expects ATR params"):
        BacktestConfig.model_validate({"runs": [run]})


def test_csv_path_present_in_example():
    assert Path("examples/data/sample_daily.csv").exists()


def test_invalid_config_without_trigger_or_exit_rules():
    run = _base_run()
    run.pop("trigger")
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
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}}]},
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
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}}]},
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
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}}]},
            },
            {
                "contract_id": "aa0d74d7-7a8d-4fe4-a20f-b5d30e935001",
                "symbol": "MSFT",
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}}]},
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
