from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import yaml
from app.config.models import AnalyzerConfig, BacktestConfig, BrokerConfig


def build_backtest_output_path(output_dir: Path) -> Path:
    backtest_id = str(uuid.uuid4())
    return output_dir / backtest_id / f"{backtest_id}.json"


def parse_inline_backtest_config(payload: BacktestRunRequest) -> dict[str, Any]:
    if payload.format == "json":
        data = json.loads(payload.config_text)
    else:
        data = yaml.safe_load(payload.config_text)
    if not isinstance(data, dict):
        raise ValueError("Config root must be an object")
    return data


def build_single_day_config_raw(payload: SingleDayBacktestRequest) -> dict[str, Any]:
    broker = payload.broker or BrokerConfig(cash=100_000.0)
    return {
        "runs": [
            {
                "run_id": f"ui_{payload.symbol}_{payload.date.isoformat()}",
                "start_date": payload.date.isoformat(),
                "end_date": payload.date.isoformat(),
                "data": {
                    "type": "alpaca",
                    "symbol": payload.symbol,
                    "interval": payload.resolution,
                    "feed": payload.feed,
                },
                "strategy": payload.strategy,
                "strategy_params": payload.strategy_params,
                "broker": broker.model_dump(),
                "analyzers": AnalyzerConfig(
                    include_equity_curve=False,
                    include_order_log=True,
                    include_trade_log=True,
                ).model_dump(),
            }
        ]
    }


def build_single_day_config(payload: SingleDayBacktestRequest) -> BacktestConfig:
    return BacktestConfig.model_validate(build_single_day_config_raw(payload))
