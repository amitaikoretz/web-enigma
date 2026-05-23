from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Callable

import backtrader as bt

from app import __version__
from app.config.models import BacktestConfig, BacktestRunConfig, DataCacheConfig, StrategyConfig
from app.data.loaders import (
    build_alpaca_data_feed_with_cache,
    build_csv_data_feed,
    build_yahoo_data_feed_with_cache,
)
from app.output.models import BacktestReport, EquityPoint, RunError, RunResult, RunSummary
from app.strategies.registry import get_strategy_spec


@dataclass(frozen=True)
class RunExecutionOptions:
    cache_enabled: bool | None = None
    cache_dir: str | None = None
    cache_refresh: bool = False


@dataclass(frozen=True)
class DataFeedBuildResult:
    feed: Any
    cache_status: str | None = None


class EquityCurveAnalyzer(bt.Analyzer):
    def __init__(self) -> None:
        self.values: list[dict[str, Any]] = []

    def next(self) -> None:
        self.values.append(
            {
                "datetime": self.strategy.datetime.datetime().isoformat(),
                "value": float(self.strategy.broker.getvalue()),
            }
        )

    def get_analysis(self) -> list[dict[str, Any]]:
        return self.values


def _build_data_feed(run: BacktestRunConfig, cache_config: DataCacheConfig, cache_refresh: bool) -> DataFeedBuildResult:
    if run.data.type == "csv":
        return DataFeedBuildResult(feed=build_csv_data_feed(run.data, run.start_date, run.end_date))
    if run.data.type == "yahoo":
        feed, cache_status = build_yahoo_data_feed_with_cache(
            run.data,
            run.start_date,
            run.end_date,
            cache_config=cache_config,
            force_refresh=cache_refresh,
        )
        return DataFeedBuildResult(feed=feed, cache_status=cache_status)
    if run.data.type == "alpaca":
        feed, cache_status = build_alpaca_data_feed_with_cache(
            run.data,
            run.start_date,
            run.end_date,
            cache_config=cache_config,
            force_refresh=cache_refresh,
        )
        return DataFeedBuildResult(feed=feed, cache_status=cache_status)
    raise ValueError(f"Unsupported data source '{run.data.type}'")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_trade_counts(trade_data: dict[str, Any]) -> tuple[int, int, int]:
    totals = trade_data.get("total", {})
    total_trades = int(totals.get("total", 0) or 0)
    won_trades = int(trade_data.get("won", {}).get("total", 0) or 0)
    lost_trades = int(trade_data.get("lost", {}).get("total", 0) or 0)
    return total_trades, won_trades, lost_trades


def _run_strategy_entries(run: BacktestRunConfig) -> list[StrategyConfig]:
    if run.strategies:
        return run.strategies
    if run.strategy is None:
        raise ValueError("Run has no strategy configuration")
    return [StrategyConfig(name=run.strategy, params=run.strategy_params)]


def _result_run_id(run: BacktestRunConfig, strategy_name: str) -> str:
    strategy_entries = _run_strategy_entries(run)
    if len(strategy_entries) == 1:
        return run.run_id
    return f"{run.run_id}:{strategy_name}"


def run_backtests(config: BacktestConfig, config_raw: dict[str, Any]) -> BacktestReport:
    return run_backtests_with_hooks(config, config_raw)


def run_backtests_with_hooks(
    config: BacktestConfig,
    config_raw: dict[str, Any],
    config_path: str | None = None,
    on_run_start: Callable[[BacktestRunConfig, int, int], None] | None = None,
    on_run_complete: Callable[[RunResult, int, int], None] | None = None,
    on_run_error: Callable[[RunResult, int, int], None] | None = None,
    on_run_cache_status: Callable[[BacktestRunConfig, str], None] | None = None,
    execution_options: RunExecutionOptions | None = None,
) -> BacktestReport:
    results: list[RunResult] = []
    total = sum(len(_run_strategy_entries(run)) for run in config.runs)

    effective_cache = config.global_config.data_cache.model_copy(deep=True)
    options = execution_options or RunExecutionOptions()
    if options.cache_enabled is not None:
        effective_cache.enabled = options.cache_enabled
    if options.cache_dir:
        effective_cache.directory = options.cache_dir

    idx = 0
    for run in config.runs:
        strategy_entries = _run_strategy_entries(run)
        for strategy_entry in strategy_entries:
            idx += 1
            if on_run_start:
                on_run_start(run, idx, total)
            try:
                result, cache_status = _run_single(
                    run=run,
                    strategy_entry=strategy_entry,
                    config=config,
                    cache_config=effective_cache,
                    cache_refresh=options.cache_refresh,
                )
            except Exception as exc:  # noqa: BLE001
                result = RunResult(
                    run_id=_result_run_id(run, strategy_entry.name),
                    name=run.name,
                    status="failed",
                    strategy=strategy_entry.name,
                    data_source=run.data.type,
                    error=RunError(type=exc.__class__.__name__, message=str(exc)),
                )
                if on_run_error:
                    on_run_error(result, idx, total)
            else:
                if on_run_cache_status and cache_status and run.data.type in {"yahoo", "alpaca"}:
                    on_run_cache_status(run, cache_status)
                if on_run_complete:
                    on_run_complete(result, idx, total)
            results.append(result)

    successful = sum(1 for r in results if r.status == "success")
    failed = len(results) - successful
    if failed == 0:
        status = "success"
    elif successful == 0:
        status = "failure"
    else:
        status = "partial_failure"

    raw_bytes = json.dumps(config_raw, sort_keys=True, default=str).encode("utf-8")
    digest = hashlib.sha256(raw_bytes).hexdigest()

    return BacktestReport(
        generated_at=datetime.now(timezone.utc),
        app_version=__version__,
        config_sha256=digest,
        input_config_path=config_path,
        input_config=config_raw,
        total_runs=len(results),
        successful_runs=successful,
        failed_runs=failed,
        status=status,
        results=results,
    )


def _run_single(
    run: BacktestRunConfig,
    strategy_entry: StrategyConfig,
    config: BacktestConfig,
    cache_config: DataCacheConfig,
    cache_refresh: bool,
) -> tuple[RunResult, str | None]:
    cerebro = bt.Cerebro(stdstats=False)
    data_feed_result = _build_data_feed(run, cache_config, cache_refresh)
    cerebro.adddata(data_feed_result.feed)

    broker = run.broker or config.global_config.default_broker
    cerebro.broker.setcash(broker.cash)
    cerebro.broker.setcommission(commission=broker.commission)
    if broker.slippage_perc > 0:
        cerebro.broker.set_slippage_perc(perc=broker.slippage_perc)

    spec = get_strategy_spec(strategy_entry.name)
    cerebro.addstrategy(spec.strategy_cls, **strategy_entry.params)

    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")
    cerebro.addanalyzer(EquityCurveAnalyzer, _name="equity")

    start_value = float(cerebro.broker.getvalue())
    strategies = cerebro.run()
    strategy = strategies[0]
    end_value = float(cerebro.broker.getvalue())

    sharpe_data = strategy.analyzers.sharpe.get_analysis()
    drawdown_data = strategy.analyzers.drawdown.get_analysis()
    trade_data = strategy.analyzers.trades.get_analysis()
    equity_raw = strategy.analyzers.equity.get_analysis()

    total_trades, won_trades, lost_trades = _extract_trade_counts(trade_data)

    summary = RunSummary(
        start_value=start_value,
        end_value=end_value,
        return_pct=((end_value - start_value) / start_value * 100.0) if start_value else 0.0,
        max_drawdown_pct=_as_float(drawdown_data.get("max", {}).get("drawdown")),
        sharpe_ratio=_as_float(sharpe_data.get("sharperatio")),
        total_trades=total_trades,
        won_trades=won_trades,
        lost_trades=lost_trades,
    )

    equity_curve = []
    if run.analyzers.include_equity_curve:
        equity_curve = [EquityPoint(**point) for point in equity_raw]

    orders = strategy.order_log if run.analyzers.include_order_log else []
    trades = strategy.trade_log if run.analyzers.include_trade_log else []

    analyzers: dict[str, Any] = {
        "sharpe": sharpe_data,
        "drawdown": drawdown_data,
        "trades": trade_data,
    }

    return RunResult(
        run_id=_result_run_id(run, strategy_entry.name),
        name=run.name,
        status="success",
        strategy=strategy_entry.name,
        data_source=run.data.type,
        summary=summary,
        analyzers=analyzers,
        orders=orders,
        trades=trades,
        equity_curve=equity_curve,
    ), data_feed_result.cache_status
