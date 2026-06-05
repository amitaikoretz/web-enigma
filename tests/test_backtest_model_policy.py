from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd

from app.backtests.model_policy import BacktestModelPolicy, LoadedModelArtifact
from app.config.models import BacktestConfig
from app.engine.runner import run_backtests
from app.strategies.candidates import EntryIntent
from app.strategies.core import Bar, PositionState, StrategyContext, StrategyDecision


def _write_trending_csv(path: Path, *, bars: int = 90) -> None:
    rows = []
    for index in range(bars):
        close = 100.0 + index * 0.5
        rows.append(
            {
                "datetime": (datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index)).isoformat(),
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.5,
                "close": close,
                "volume": 10_000 + index * 100,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_delayed_breakout_csv(path: Path, *, flat_bars: int = 70, trend_bars: int = 40) -> None:
    rows = []
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    for index in range(flat_bars):
        close = 100.0
        rows.append(
            {
                "datetime": (timestamp + timedelta(days=index)).isoformat(),
                "open": close - 0.2,
                "high": close + 0.3,
                "low": close - 0.3,
                "close": close,
                "volume": 10_000 + index * 20,
            }
        )
    for index in range(trend_bars):
        close = 100.0 + (index + 1) * 0.75
        rows.append(
            {
                "datetime": (timestamp + timedelta(days=flat_bars + index)).isoformat(),
                "open": close - 0.2,
                "high": close + 0.4,
                "low": close - 0.5,
                "close": close,
                "volume": 12_000 + index * 100,
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def _write_model_artifact(
    path: Path,
    *,
    artifact_type: str,
    feature_cols: list[str],
    coef: list[float],
    intercept: float,
    scaler_mean: list[float] | None = None,
    scaler_scale: list[float] | None = None,
) -> None:
    payload: dict[str, object] = {
        "type": artifact_type,
        "feature_cols": feature_cols,
        "coef": coef,
        "intercept": intercept,
    }
    if scaler_mean is not None:
        payload["scaler_mean"] = scaler_mean
    if scaler_scale is not None:
        payload["scaler_scale"] = scaler_scale
    path.write_text(json.dumps(payload), encoding="utf-8")


def _make_context(*, bars: int = 90) -> StrategyContext:
    history: list[Bar] = []
    for index in range(bars):
        close = 100.0 + index * 0.5
        history.append(
            Bar(
                timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=index),
                open=close - 0.2,
                high=close + 0.4,
                low=close - 0.5,
                close=close,
                volume=10_000 + index * 100,
            )
        )
    return StrategyContext(
        bar=history[-1],
        bars=tuple(history),
        position=PositionState(),
        symbol="AAPL",
        equity=100_000.0,
    )


def _entry_intent() -> EntryIntent:
    return EntryIntent(
        entry_price=145.0,
        planned_stop_pct=0.01,
        planned_target_pct=0.02,
        planned_horizon_bars=10,
        signal_score=1.0,
        signal_reason="breakout",
        metadata={"source": "test"},
    )


def test_backtest_run_config_accepts_optional_model_policy(tmp_path: Path) -> None:
    forecast_path = tmp_path / "forecast.json"
    risk_path = tmp_path / "risk.json"
    _write_model_artifact(
        forecast_path,
        artifact_type="ridge",
        feature_cols=["trend_slope_20"],
        coef=[1.0],
        intercept=0.001,
    )
    _write_model_artifact(
        risk_path,
        artifact_type="ridge",
        feature_cols=["realized_vol_20"],
        coef=[1.0],
        intercept=0.001,
    )

    base_run = {
        "run_id": "r1",
        "start_date": "2024-01-01",
        "end_date": "2024-04-01",
        "data": {"type": "csv", "path": str(tmp_path / "prices.csv")},
        "trigger": {"name": "breakout_channel", "params": {"lookback": 5, "stake": 1, "stop_loss_pct": 0.01, "take_profit_pct": 0.02, "max_hold_bars": 999}},
        "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 999}}]},
    }
    _write_trending_csv(tmp_path / "prices.csv")

    configs = [
        {},
        {"forecast_model": {"model_artifact_path": str(forecast_path)}},
        {"risk_model": {"model_artifact_path": str(risk_path)}},
        {
            "forecast_model": {"model_artifact_path": str(forecast_path)},
            "risk_model": {"model_artifact_path": str(risk_path)},
        },
    ]
    for model_policy in configs:
        config = BacktestConfig.model_validate({"runs": [{**base_run, "model_policy": model_policy}]})
        assert config.runs[0].model_policy is not None


def test_model_policy_apply_supports_forecast_risk_and_combined_paths() -> None:
    context = _make_context()
    decision = StrategyDecision.buy(1.0, "breakout", entry_intent=_entry_intent())

    forecast_model = LoadedModelArtifact(
        artifact_path=Path("/tmp/forecast.json"),
        family="forecast",
        target_key="forecast_return",
        feature_columns=["trend_slope_20"],
        artifact_type="ridge",
        coefficients=[10.0],
        intercept=0.002,
    )
    risk_model = LoadedModelArtifact(
        artifact_path=Path("/tmp/risk.json"),
        family="risk",
        target_key="mae",
        feature_columns=["realized_vol_20"],
        artifact_type="ridge",
        coefficients=[10.0],
        intercept=0.001,
    )

    forecast_only = BacktestModelPolicy(
        config=BacktestConfig.model_validate(
            {
                "runs": [
                    {
                        "run_id": "r1",
                        "start_date": "2024-01-01",
                        "end_date": "2024-04-01",
                        "data": {"type": "csv", "path": str(Path("/tmp/prices.csv"))},
                        "trigger": {"name": "breakout_channel", "params": {"lookback": 5, "stake": 1, "stop_loss_pct": 0.01, "take_profit_pct": 0.02, "max_hold_bars": 999}},
                        "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 999}}]},
                        "model_policy": {
                            "forecast_model": {"model_artifact_path": str(Path("/tmp/forecast.json"))},
                            "threshold_bps": 1.0,
                            "target_edge_bps": 5.0,
                            "max_risk_fraction": 0.001,
                        },
                    }
                ]
            }
        ).runs[0].model_policy,
        strategy_id="breakout_channel|exits:manual",
        data_source="csv",
        fill_model="close",
        forecast_model=forecast_model,
        risk_model=None,
    )
    forecast_decision = forecast_only.apply(context, decision)
    assert forecast_decision.action == "buy"
    assert forecast_decision.entry_intent is not None
    assert forecast_decision.entry_intent.metadata["model_policy"]["forecast"]["score"] is not None

    risk_only = BacktestModelPolicy(
        config=BacktestConfig.model_validate(
            {
                "runs": [
                    {
                        "run_id": "r1",
                        "start_date": "2024-01-01",
                        "end_date": "2024-04-01",
                        "data": {"type": "csv", "path": str(Path("/tmp/prices.csv"))},
                        "trigger": {"name": "breakout_channel", "params": {"lookback": 5, "stake": 1, "stop_loss_pct": 0.01, "take_profit_pct": 0.02, "max_hold_bars": 999}},
                        "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 999}}]},
                        "model_policy": {
                            "risk_model": {"model_artifact_path": str(Path("/tmp/risk.json"))},
                            "threshold_bps": 1.0,
                            "target_edge_bps": 5.0,
                            "max_risk_fraction": 0.001,
                        },
                    }
                ]
            }
        ).runs[0].model_policy,
        strategy_id="breakout_channel|exits:manual",
        data_source="csv",
        fill_model="close",
        forecast_model=None,
        risk_model=risk_model,
    )
    risk_decision = risk_only.apply(context, decision)
    assert risk_decision.action == "buy"
    assert risk_decision.entry_intent is not None
    assert risk_decision.entry_intent.metadata["model_policy"]["risk"]["score"] is not None

    combined = BacktestModelPolicy(
        config=BacktestConfig.model_validate(
            {
                "runs": [
                    {
                        "run_id": "r1",
                        "start_date": "2024-01-01",
                        "end_date": "2024-04-01",
                        "data": {"type": "csv", "path": str(Path("/tmp/prices.csv"))},
                        "trigger": {"name": "breakout_channel", "params": {"lookback": 5, "stake": 1, "stop_loss_pct": 0.01, "take_profit_pct": 0.02, "max_hold_bars": 999}},
                        "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 999}}]},
                        "model_policy": {
                            "forecast_model": {"model_artifact_path": str(Path("/tmp/forecast.json"))},
                            "risk_model": {"model_artifact_path": str(Path("/tmp/risk.json"))},
                            "threshold_bps": 1.0,
                            "target_edge_bps": 5.0,
                            "max_risk_fraction": 0.001,
                        },
                    }
                ]
            }
        ).runs[0].model_policy,
        strategy_id="breakout_channel|exits:manual",
        data_source="csv",
        fill_model="close",
        forecast_model=forecast_model,
        risk_model=risk_model,
    )
    combined_decision = combined.apply(context, decision)
    assert combined_decision.action == "buy"
    assert combined_decision.entry_intent is not None
    assert combined_decision.entry_intent.metadata["model_policy"]["mode"] == "combined"


def test_backtest_model_policy_changes_entry_size_and_persists_metadata(tmp_path: Path) -> None:
    csv_path = tmp_path / "prices.csv"
    forecast_path = tmp_path / "forecast.json"
    risk_path = tmp_path / "risk.json"
    _write_delayed_breakout_csv(csv_path)
    _write_model_artifact(
        forecast_path,
        artifact_type="ridge",
        feature_cols=["trend_slope_20"],
        coef=[5.0],
        intercept=0.003,
    )
    _write_model_artifact(
        risk_path,
        artifact_type="ridge",
        feature_cols=["realized_vol_20"],
        coef=[5.0],
        intercept=0.001,
    )

    base_raw = {
        "runs": [
            {
                "run_id": "r1",
                "start_date": "2024-01-01",
                "end_date": "2024-04-30",
                "data": {"type": "csv", "path": str(csv_path)},
                "trigger": {"name": "breakout_channel", "params": {"lookback": 5, "stake": 1, "stop_loss_pct": 0.01, "take_profit_pct": 0.02, "max_hold_bars": 999}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 999}}]},
                "analyzers": {"include_candidate_log": True, "include_trade_log": True, "include_order_log": True},
            }
        ]
    }
    model_raw = {
        "runs": [
            {
                **base_raw["runs"][0],
                "model_policy": {
                    "forecast_model": {"model_artifact_path": str(forecast_path)},
                    "risk_model": {"model_artifact_path": str(risk_path)},
                    "threshold_bps": 1.0,
                    "target_edge_bps": 5.0,
                    "max_risk_fraction": 0.005,
                },
            }
        ]
    }

    base_config = BacktestConfig.model_validate(base_raw, context={"config_base_dir": tmp_path})
    model_config = BacktestConfig.model_validate(model_raw, context={"config_base_dir": tmp_path})

    base_report = run_backtests(base_config, base_raw)
    model_report = run_backtests(model_config, model_raw)

    assert base_report.results[0].trades
    assert model_report.results[0].trades
    assert base_report.results[0].trades[0].size != model_report.results[0].trades[0].size
    assert model_report.results[0].candidates
    model_candidate = model_report.results[0].candidates[0]
    assert "model_policy" in model_candidate.metadata
    assert model_candidate.metadata["model_policy"]["mode"] == "combined"
