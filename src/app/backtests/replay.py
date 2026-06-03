from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pandas as pd
import yaml

from app.config.models import BacktestConfig, BacktestRunConfig, DataCacheConfig
from app.data.loaders import (
    build_alpaca_data_feed_with_cache,
    build_csv_data_feed,
    build_yahoo_data_feed_with_cache,
)
from app.backtests.models import (
    BacktestDetailResponse,
    BacktestTradeReplayCapsule,
)
from app.replay_debug import (
    ReplayDebugTarget,
    clear_trade_replay_debug_target as _clear_trade_replay_debug_target,
    install_trade_replay_debug_target as _install_trade_replay_debug_target,
    maybe_break_for_trade_replay as _maybe_break_for_trade_replay,
)

REPLAY_TARGET_METHODS = (
    "app.strategies.implementations.PortableBacktestingStrategy.next",
    "app.strategies.components.ComposableStrategyCore.on_bar",
)
DEFAULT_REPLAY_PADDING_MINUTES = 10


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _timestamp_to_utc(value: datetime | pd.Timestamp | Any) -> pd.Timestamp | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize(UTC)
    else:
        ts = ts.tz_convert(UTC)
    return ts


def _resolve_run(config: BacktestConfig, run_id: str) -> BacktestRunConfig | None:
    for run in config.runs:
        if run.run_id == run_id:
            return run
    return None


def _build_run_data_feed(run: BacktestRunConfig, cache_config: DataCacheConfig | None) -> pd.DataFrame:
    if run.data.type == "csv":
        return build_csv_data_feed(run.data, run.start_date, run.end_date)
    if run.data.type == "yahoo":
        feed, _ = build_yahoo_data_feed_with_cache(
            run.data,
            run.start_date,
            run.end_date,
            cache_config=cache_config,
            force_refresh=False,
        )
        return feed
    if run.data.type == "alpaca":
        feed, _ = build_alpaca_data_feed_with_cache(
            run.data,
            run.start_date,
            run.end_date,
            cache_config=cache_config,
            force_refresh=False,
        )
        return feed
    raise ValueError(f"Unsupported data source '{run.data.type}'")


def _resolve_target_bar_index(
    config: BacktestConfig,
    capsule: BacktestTradeReplayCapsule,
) -> int | None:
    run = _resolve_run(config, capsule.run_id)
    if run is None:
        return None

    target_time = _parse_iso_datetime(capsule.trade_entry_time if capsule.break_at == "entry" else capsule.trade_exit_time)
    if target_time is None:
        return None

    feed = _build_run_data_feed(run, config.global_config.data_cache)
    if feed.empty:
        return None

    target_ts = _timestamp_to_utc(target_time)
    if target_ts is None:
        return None

    for index, bar_timestamp in enumerate(feed.index):
        current_ts = _timestamp_to_utc(bar_timestamp)
        if current_ts is None:
            continue
        if current_ts >= target_ts:
            return index
    return None


def _coerce_report_input_config(detail: BacktestDetailResponse) -> dict[str, Any]:
    if detail.report is None:
        raise ValueError("Backtest report is not available; replay capsules require a persisted report")
    if not isinstance(detail.report.input_config, dict):
        raise ValueError("Backtest report input_config must be a mapping")
    return detail.report.input_config


def _select_run_config(input_config: dict[str, Any], run_id: str) -> dict[str, Any]:
    runs = input_config.get("runs")
    if not isinstance(runs, list):
        raise ValueError("Backtest config does not contain a runs array")

    for run in runs:
        if isinstance(run, dict) and run.get("run_id") == run_id:
            return json.loads(json.dumps({"runs": [run]}, default=str))

    raise ValueError(f"Run '{run_id}' was not found in the backtest config")


def _trade_focus_window(trade_entry_time: str | None, trade_exit_time: str | None) -> tuple[str | None, str | None]:
    from_time = _parse_iso_datetime(trade_entry_time or trade_exit_time)
    to_time = _parse_iso_datetime(trade_exit_time or trade_entry_time)
    if from_time is None or to_time is None:
        return None, None

    padding = timedelta(minutes=DEFAULT_REPLAY_PADDING_MINUTES)
    return (from_time - padding).isoformat(), (to_time + padding).isoformat()


def build_trade_replay_capsule(
    detail: BacktestDetailResponse,
    *,
    run_id: str,
    trade_index: int,
) -> BacktestTradeReplayCapsule:
    input_config = _coerce_report_input_config(detail)
    report = detail.report
    assert report is not None  # for type-checkers; validated above

    run_result = next((result for result in report.results if result.run_id == run_id), None)
    if run_result is None:
        raise ValueError(f"Run '{run_id}' was not found in backtest '{detail.metadata.id}'")
    if trade_index < 0 or trade_index >= len(run_result.trades):
        raise ValueError(
            f"Trade index {trade_index} is out of range for run '{run_id}' ({len(run_result.trades)} trade(s))"
        )

    trade = run_result.trades[trade_index]
    trade_entry_time = trade.entry_datetime or trade.datetime
    trade_exit_time = trade.datetime or trade.entry_datetime
    focus_window_start, focus_window_end = _trade_focus_window(trade_entry_time, trade_exit_time)
    replay_config = _select_run_config(input_config, run_id)
    config_text = yaml.safe_dump(replay_config, default_flow_style=False, sort_keys=False)
    config_sha256 = hashlib.sha256(config_text.encode("utf-8")).hexdigest()

    return BacktestTradeReplayCapsule(
        backtest_id=detail.metadata.id,
        run_id=run_id,
        run_name=run_result.name,
        run_symbol=run_result.symbol,
        run_strategy=run_result.strategy,
        trade_index=trade_index,
        target_methods=list(REPLAY_TARGET_METHODS),
        break_at="entry" if trade.entry_datetime else "exit",
        trade=trade,
        trade_entry_time=trade_entry_time,
        trade_exit_time=trade_exit_time,
        focus_window_start=focus_window_start,
        focus_window_end=focus_window_end,
        config_text=config_text,
        config_sha256=config_sha256,
    )


def encode_trade_replay_capsule(capsule: BacktestTradeReplayCapsule) -> str:
    raw = capsule.model_dump_json().encode("utf-8")
    return base64.b64encode(raw).decode("ascii")


def build_trade_replay_launch_config(capsule: BacktestTradeReplayCapsule) -> dict[str, Any]:
    capsule_b64 = encode_trade_replay_capsule(capsule)
    return {
        "name": f"Replay trade: {capsule.backtest_id} / {capsule.run_id} #{capsule.trade_index + 1}",
        "type": "debugpy",
        "request": "launch",
        "python": "${command:python.interpreterPath}",
        "module": "app.cli",
        "cwd": "${workspaceFolder}",
        "console": "integratedTerminal",
        "env": {
            "PYTHONPATH": "${workspaceFolder}/src",
            "ALPACA_API_KEY": "${env:ALPACA_API_KEY}",
            "ALPACA_SECRET_KEY": "${env:ALPACA_SECRET_KEY}",
        },
        "args": [
            "replay-trade",
            "--capsule-b64",
            capsule_b64,
        ],
        "justMyCode": True,
    }


def install_trade_replay_debug_target(capsule: BacktestTradeReplayCapsule) -> None:
    target_bar_time = capsule.trade_entry_time if capsule.break_at == "entry" else capsule.trade_exit_time
    target_bar_index = capsule.trade.entry_bar_index if capsule.break_at == "entry" else capsule.trade.exit_bar_index
    parsed_target = _parse_iso_datetime(target_bar_time) if target_bar_time is not None else None
    if parsed_target is None and target_bar_index is None:
        raise ValueError("Replay capsule does not contain a usable target timestamp or bar index")
    _install_trade_replay_debug_target(
        ReplayDebugTarget(
            target_bar_index=target_bar_index,
            target_bar_time=parsed_target,
            target_methods=tuple(capsule.target_methods) or REPLAY_TARGET_METHODS,
            break_at=capsule.break_at,
        )
    )


def clear_trade_replay_debug_target() -> None:
    _clear_trade_replay_debug_target()


def resolve_trade_replay_target_bar_index(
    config: BacktestConfig,
    capsule: BacktestTradeReplayCapsule,
) -> int | None:
    return _resolve_target_bar_index(config, capsule)


def maybe_break_for_trade_replay(
    method_name: str,
    *,
    bar_index: int | None = None,
    timestamp: str | None = None,
) -> None:
    _maybe_break_for_trade_replay(method_name, bar_index=bar_index, timestamp=timestamp)
