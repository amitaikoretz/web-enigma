from datetime import datetime, timezone

import pytest

from app.output.models import BacktestReport
from app.strategies.exit_rules import list_exit_rules, validate_exit_rule_params
from app.strategies.triggers import list_triggers, validate_trigger_params


def test_registry_has_demo_triggers_and_exit_rules():
    trigger_names = {s.name for s in list_triggers()}
    exit_rule_names = {s.name for s in list_exit_rules()}
    assert {
        "sma_cross",
        "rsi_reversion",
        "buy_and_hold",
        "breakout_channel",
        "buy_oco_atr",
        "vwap_pullback",
        "volume_rally",
        "fast_upswing",
    } <= trigger_names
    assert {
        "fixed_pct_oco",
        "max_hold_bars",
        "sma_cross_down",
        "rsi_overbought",
        "atr_oco",
        "atr_trailing",
        "atr_take_profit",
        "atr_trailing_stop",
        "atr_profit_protect_stop",
        "vwap_pullback_manage",
        "volume_rally_atr",
    } <= exit_rule_names


def test_registry_param_validation():
    parsed = validate_trigger_params("sma_cross", {"fast": 3, "slow": 8, "stake": 2})
    assert parsed["fast"] == 3
    oco_entry = validate_trigger_params("buy_oco_atr", {"stake": 2, "atr_period": 10, "entry_sma": 20})
    assert oco_entry["atr_period"] == 10
    rally_parsed = validate_trigger_params(
        "volume_rally",
        {"stake": 2, "volume_window": 10, "macd_fast": 5, "macd_slow": 10},
    )
    assert rally_parsed["volume_window"] == 10
    assert rally_parsed["session_start_minutes"] == 0
    assert rally_parsed["min_confirmations"] == 3
    tiered = validate_trigger_params("volume_rally", {"min_confirmations": 4})
    assert tiered["min_confirmations"] == 4
    upswing = validate_trigger_params("fast_upswing", {"return_lookback": 5, "volume_window": 20})
    assert upswing["min_consecutive_up_bars"] == 3
    assert upswing["require_vwap"] is True
    vwap_pullback = validate_trigger_params("vwap_pullback", {"benchmark_symbol": "QQQ"})
    assert vwap_pullback["benchmark_symbol"] == "QQQ"
    assert vwap_pullback["benchmark_resolution_minutes"] == 15
    assert vwap_pullback["min_closes_above_vwap"] == 2
    vwap_manage = validate_exit_rule_params("vwap_pullback_manage", {"partial_trim_portion": 0.5})
    assert vwap_manage["partial_trim_portion"] == 0.5
    with pytest.raises(ValueError):
        validate_trigger_params("sma_cross", {"fast": 0, "slow": 8})
    with pytest.raises(ValueError):
        validate_exit_rule_params("atr_trailing", {"trail_atr_mult": 0})
    with pytest.raises(ValueError):
        validate_exit_rule_params("atr_profit_protect_stop", {"sl_atr_mult": 0})
    with pytest.raises(ValueError):
        validate_trigger_params("volume_rally", {"macd_fast": 12, "macd_slow": 8})
    with pytest.raises(ValueError):
        validate_trigger_params("volume_rally", {"min_confirmations": 1})
    with pytest.raises(ValueError):
        validate_trigger_params(
            "volume_rally",
            {"benchmark_symbol": "SPY", "benchmark_require_above_sma": False, "benchmark_adx_min": 0},
        )


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
