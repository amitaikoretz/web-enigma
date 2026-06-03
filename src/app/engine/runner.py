from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

import pandas as pd
from backtesting import Backtest

from app import __version__
from app.config.models import BacktestConfig, BacktestRunConfig, DataCacheConfig
from app.data.loaders import (
    build_alpaca_data_feed_with_cache,
    build_csv_data_feed,
    build_yahoo_data_feed_with_cache,
)
from app.engine.aggregates import compute_report_aggregates
from app.engine.metrics import (
    build_candidate_records,
    build_order_records,
    build_rejection_records,
    compute_candidate_diagnostics,
    compute_filter_diagnostics,
    compute_risk_metrics,
    compute_trade_diagnostics,
    enrich_trade_records,
)
from app.output.models import (
    BacktestReport,
    EquityPoint,
    FeatureSnapshotRecord,
    OutcomeLabelRecord,
    RunError,
    RunResult,
    RunSummary,
)
from app.risk.build.run_auxiliary import build_risk_auxiliary_for_run
from app.risk.models import RiskDatasetConfig, RunRiskAuxiliaryRows
from app.strategies.implementations import build_portable_strategy_adapter
from app.strategies.factory import build_strategy_core, composed_strategy_id


@dataclass(frozen=True)
class RunExecutionOptions:
    cache_enabled: bool | None = None
    cache_dir: str | None = None
    cache_refresh: bool = False
    risk_dataset_config: RiskDatasetConfig | None = None
    on_run_bar_progress: Callable[[int, int, int, int], None] | None = None


@dataclass
class BacktestExecutionResult:
    report: BacktestReport
    risk_auxiliary_by_run: dict[str, tuple[list[OutcomeLabelRecord], list[FeatureSnapshotRecord]]] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class DataFeedBuildResult:
    feed: pd.DataFrame
    cache_status: str | None = None


def _benchmark_symbol_for_strategy(strategy_name: str, params: dict[str, Any]) -> str | None:
    if strategy_name != "volume_rally":
        return None
    symbol = str(params.get("benchmark_symbol", "")).strip().upper()
    return symbol or None


def _load_benchmark_feed(
    run: BacktestRunConfig,
    benchmark_symbol: str,
    cache_config: DataCacheConfig,
    cache_refresh: bool,
) -> pd.DataFrame:
    if run.data.type not in {"yahoo", "alpaca"}:
        raise ValueError(
            f"Benchmark filter symbol '{benchmark_symbol}' requires a yahoo or alpaca data source"
        )
    if run.data.type == "yahoo":
        data = run.data.model_copy(update={"symbol": benchmark_symbol})
        feed, _ = build_yahoo_data_feed_with_cache(
            data,
            run.start_date,
            run.end_date,
            cache_config=cache_config,
            force_refresh=cache_refresh,
        )
        return feed
    data = run.data.model_copy(update={"symbol": benchmark_symbol})
    feed, _ = build_alpaca_data_feed_with_cache(
        data,
        run.start_date,
        run.end_date,
        cache_config=cache_config,
        force_refresh=cache_refresh,
    )
    return feed


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
        if pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_trade_counts(trade_data: dict[str, Any]) -> tuple[int, int, int]:
    totals = trade_data.get("total", {})
    total_trades = int(totals.get("total", 0) or 0)
    won_trades = int(trade_data.get("won", {}).get("total", 0) or 0)
    lost_trades = int(trade_data.get("lost", {}).get("total", 0) or 0)
    return total_trades, won_trades, lost_trades


def _result_run_id(run: BacktestRunConfig) -> str:
    return run.run_id


def _build_trade_analyzer_like(closed_trades: pd.DataFrame) -> dict[str, Any]:
    if closed_trades.empty:
        return {
            "total": {"total": 0, "open": 0, "closed": 0},
            "won": {"total": 0},
            "lost": {"total": 0},
        }

    won = int((closed_trades["PnL"] > 0).sum())
    lost = int((closed_trades["PnL"] <= 0).sum())
    total = int(len(closed_trades))
    return {
        "total": {"total": total, "open": 0, "closed": total},
        "won": {"total": won},
        "lost": {"total": lost},
    }


def _strategy_symbol(run: BacktestRunConfig) -> str | None:
    if run.data.type in {"yahoo", "alpaca"}:
        return run.data.symbol
    return None


def run_backtests(config: BacktestConfig, config_raw: dict[str, Any]) -> BacktestReport:
    return run_backtests_with_hooks(config, config_raw).report


def run_backtests_with_hooks(
    config: BacktestConfig,
    config_raw: dict[str, Any],
    config_path: str | None = None,
    on_run_start: Callable[[BacktestRunConfig, int, int], None] | None = None,
    on_run_complete: Callable[[RunResult, int, int], None] | None = None,
    on_run_error: Callable[[RunResult, int, int], None] | None = None,
    on_run_cache_status: Callable[[BacktestRunConfig, str], None] | None = None,
    execution_options: RunExecutionOptions | None = None,
) -> BacktestExecutionResult:
    results: list[RunResult] = []
    risk_auxiliary_by_run: dict[str, tuple[list[OutcomeLabelRecord], list[FeatureSnapshotRecord]]] = {}
    total = len(config.runs)

    effective_cache = config.global_config.data_cache.model_copy(deep=True)
    options = execution_options or RunExecutionOptions()
    if options.cache_enabled is not None:
        effective_cache.enabled = options.cache_enabled
    if options.cache_dir:
        effective_cache.directory = options.cache_dir

    idx = 0
    for run in config.runs:
        idx += 1
        if on_run_start:
            on_run_start(run, idx, total)
        try:
            result, cache_status, risk_auxiliary = _run_single(
                run=run,
                config=config,
                cache_config=effective_cache,
                cache_refresh=options.cache_refresh,
                risk_dataset_config=options.risk_dataset_config,
                run_idx=idx,
                total_runs=total,
                on_run_bar_progress=options.on_run_bar_progress,
            )
        except Exception as exc:  # noqa: BLE001
            trigger_name = run.trigger.name if run.trigger is not None else "unknown_trigger"
            result = RunResult(
                run_id=_result_run_id(run),
                name=run.name,
                status="failed",
                strategy=trigger_name,
                data_source=run.data.type,
                error=RunError(type=exc.__class__.__name__, message=str(exc)),
            )
            risk_auxiliary = RunRiskAuxiliaryRows()
            if on_run_error:
                on_run_error(result, idx, total)
        else:
            if risk_auxiliary.labels or risk_auxiliary.features:
                risk_auxiliary_by_run[result.run_id] = (risk_auxiliary.labels, risk_auxiliary.features)
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

    aggregates = compute_report_aggregates(results)

    return BacktestExecutionResult(
        report=BacktestReport(
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
            aggregates=aggregates,
        ),
        risk_auxiliary_by_run=risk_auxiliary_by_run,
    )


def _run_single(
    run: BacktestRunConfig,
    config: BacktestConfig,
    cache_config: DataCacheConfig,
    cache_refresh: bool,
    risk_dataset_config: RiskDatasetConfig | None = None,
    *,
    run_idx: int | None = None,
    total_runs: int | None = None,
    on_run_bar_progress: Callable[[int, int, int, int], None] | None = None,
) -> tuple[RunResult, str | None, RunRiskAuxiliaryRows]:
    data_feed_result = _build_data_feed(run, cache_config, cache_refresh)
    bar_progress_total = len(data_feed_result.feed)

    broker = run.broker or config.global_config.default_broker
    if run.trigger is None or run.exit_rules is None:
        raise ValueError("Run is missing trigger/exit rules selection")
    benchmark_symbol = _benchmark_symbol_for_strategy(run.trigger.name, run.trigger.params)
    benchmark_feed = None
    if benchmark_symbol:
        benchmark_feed = _load_benchmark_feed(run, benchmark_symbol, cache_config, cache_refresh)

    bar_progress_callback = None
    if on_run_bar_progress is not None and run_idx is not None and total_runs is not None:

        def bar_progress_callback(bar_idx: int) -> None:
            on_run_bar_progress(run_idx, total_runs, bar_idx, bar_progress_total)

    strategy_cls = build_portable_strategy_adapter(
        strategy_name=composed_strategy_id(trigger=run.trigger, exit_rules=run.exit_rules),
        strategy_factory=lambda _: build_strategy_core(trigger=run.trigger, exit_rules=run.exit_rules),
        strategy_params={},
        symbol=_strategy_symbol(run),
        benchmark_feed=benchmark_feed,
        include_candidate_log=run.analyzers.include_candidate_log,
        fill_model=run.execution.fill_model,
        bar_progress_callback=bar_progress_callback,
    )

    bt = Backtest(
        data_feed_result.feed,
        strategy_cls,
        cash=float(broker.cash),
        commission=float(broker.commission),
        spread=float(broker.slippage_perc),
        trade_on_close=run.execution.fill_model == "close",
        finalize_trades=True,
    )
    stats = bt.run()

    start_value = float(broker.cash)
    end_value = float(stats.get("Equity Final [$]", broker.cash))

    drawdown = _as_float(stats.get("Max. Drawdown [%]"))
    sharpe = _as_float(stats.get("Sharpe Ratio"))

    closed_trades = stats.get("_trades")
    if not isinstance(closed_trades, pd.DataFrame):
        closed_trades = pd.DataFrame()

    trade_data = _build_trade_analyzer_like(closed_trades)
    total_trades, won_trades, lost_trades = _extract_trade_counts(trade_data)

    equity_series = stats.get("_equity_curve")
    equity_curve: list[EquityPoint] = []
    if isinstance(equity_series, pd.DataFrame) and "Equity" in equity_series.columns:
        equity_curve = [
            EquityPoint(datetime=idx.isoformat(), value=float(val))
            for idx, val in equity_series["Equity"].items()
        ]

    strategy_obj = stats.get("_strategy")
    raw_orders: list[dict[str, Any]] = []
    raw_trades: list[dict[str, Any]] = []
    raw_rejections: list[dict[str, Any]] = []
    raw_candidates: list[Any] = []
    if strategy_obj is not None:
        raw_orders = getattr(strategy_obj, "order_log", []) if run.analyzers.include_order_log else []
        raw_trades = getattr(strategy_obj, "trade_log", []) if run.analyzers.include_trade_log else []
        raw_rejections = getattr(strategy_obj, "rejection_log", [])
        if run.analyzers.include_candidate_log:
            raw_candidates = getattr(strategy_obj, "candidate_log", [])

    candidates = build_candidate_records(raw_candidates)
    candidate_diagnostics = compute_candidate_diagnostics(candidates)

    orders = build_order_records(raw_orders)
    trades = enrich_trade_records(raw_trades, closed_trades)
    rejections = build_rejection_records(raw_rejections)

    return_pct = ((end_value - start_value) / start_value * 100.0) if start_value else 0.0
    trade_diagnostics = compute_trade_diagnostics(
        trades,
        orders,
        start_value=start_value,
        end_value=end_value,
    )
    filter_diagnostics = compute_filter_diagnostics(rejections, total_trades=total_trades)
    risk_metrics = compute_risk_metrics(stats, return_pct=return_pct)

    analyzers: dict[str, Any] = {
        "sharpe": {"sharperatio": sharpe},
        "drawdown": {"max": {"drawdown": drawdown}},
        "trades": trade_data,
        "execution": {"fill_model": run.execution.fill_model},
        "include_candidate_log": run.analyzers.include_candidate_log,
        "include_risk_auxiliary": run.analyzers.include_risk_auxiliary,
        "resolution": run.data.interval if hasattr(run.data, "interval") else None,
        "trade_diagnostics": trade_diagnostics.model_dump(),
        "filter_diagnostics": filter_diagnostics.model_dump(),
        "risk_metrics": risk_metrics.model_dump(),
        "distributions": (
            trade_diagnostics.distributions.model_dump()
            if trade_diagnostics.distributions is not None
            else None
        ),
        "filters": {
            "rejections": [rejection.model_dump() for rejection in rejections],
            **filter_diagnostics.model_dump(),
        },
        "candidate_diagnostics": candidate_diagnostics.model_dump(),
    }

    summary = RunSummary(
        start_value=start_value,
        end_value=end_value,
        return_pct=return_pct,
        max_drawdown_pct=drawdown,
        sharpe_ratio=sharpe,
        total_trades=total_trades,
        won_trades=won_trades,
        lost_trades=lost_trades,
        trade_diagnostics=trade_diagnostics,
        filter_diagnostics=filter_diagnostics,
        risk_metrics=risk_metrics,
    )

    result = RunResult(
        run_id=_result_run_id(run),
        name=run.name,
        status="success",
        strategy=composed_strategy_id(trigger=run.trigger, exit_rules=run.exit_rules),
        symbol=_strategy_symbol(run),
        data_source=run.data.type,
        summary=summary,
        analyzers=analyzers,
        orders=orders,
        trades=trades,
        rejections=rejections,
        candidates=candidates if run.analyzers.include_candidate_log else [],
        equity_curve=equity_curve if run.analyzers.include_equity_curve else [],
    )

    risk_auxiliary = RunRiskAuxiliaryRows()
    if run.analyzers.include_risk_auxiliary and candidates:
        risk_auxiliary = build_risk_auxiliary_for_run(
            result=result,
            run=run,
            symbol_frame=data_feed_result.feed,
            benchmark_frame=benchmark_feed,
            config=risk_dataset_config,
        )

    return result, data_feed_result.cache_status, risk_auxiliary
