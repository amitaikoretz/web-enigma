from datetime import datetime, timezone

import pytest

from app.output.models import BacktestReport
from app.strategies.registry import list_strategies, validate_strategy_params


def test_registry_has_demo_strategies():
    names = {s.name for s in list_strategies()}
    assert {
        "sma_cross",
        "rsi_reversion",
        "buy_and_hold",
        "breakout_channel",
        "buy_oco_atr_tp_sl",
        "buy_oco_atr_tp_trailing",
        "volume_rally",
    } <= names


def test_registry_param_validation():
    parsed = validate_strategy_params("sma_cross", {"fast": 3, "slow": 8, "stake": 2})
    assert parsed["fast"] == 3
    oco_parsed = validate_strategy_params("buy_oco_atr_tp_sl", {"stake": 2, "atr_period": 10, "sl_atr_mult": 1.2})
    assert oco_parsed["atr_period"] == 10
    rally_parsed = validate_strategy_params("volume_rally", {"stake": 2, "volume_window": 10, "macd_fast": 5, "macd_slow": 10})
    assert rally_parsed["volume_window"] == 10
    with pytest.raises(ValueError):
        validate_strategy_params("sma_cross", {"fast": 0, "slow": 8})
    with pytest.raises(ValueError):
        validate_strategy_params("buy_oco_atr_tp_trailing", {"trail_atr_mult": 0})
    with pytest.raises(ValueError):
        validate_strategy_params("volume_rally", {"macd_fast": 12, "macd_slow": 8})


def test_output_model_validation():
    payload = {
        "generated_at": datetime.now(timezone.utc),
        "app_version": "0.1.0",
        "config_sha256": "abc",
        "total_runs": 1,
        "successful_runs": 1,
        "failed_runs": 0,
        "status": "success",
        "results": [
            {
                "run_id": "r1",
                "status": "success",
                "strategy": "sma_cross",
                "data_source": "csv",
                "summary": {
                    "start_value": 10000.0,
                    "end_value": 10100.0,
                    "return_pct": 1.0,
                    "total_trades": 1,
                    "won_trades": 1,
                    "lost_trades": 0,
                },
            }
        ],
    }
    report = BacktestReport.model_validate(payload)
    assert report.total_runs == 1
