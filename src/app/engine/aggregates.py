from __future__ import annotations

import math
from collections import defaultdict
from statistics import mean

from app.engine.metrics import compute_filter_diagnostics, compute_trade_diagnostics
from app.output.models import (
    EquityPoint,
    OrderRecord,
    PortfolioAggregate,
    RejectionRecord,
    ReportAggregates,
    RunResult,
    RunSummary,
    StrategyAggregate,
    TradeRecord,
)

MAX_EQUITY_CURVE_POINTS = 2000

# Approximate bars per year by resolution string for Sharpe annualization.
_BARS_PER_YEAR: dict[str, float] = {
    "1m": 252 * 390,
    "5m": 252 * 78,
    "15m": 252 * 26,
    "30m": 252 * 13,
    "1h": 252 * 6.5,
    "1d": 252,
    "1wk": 52,
    "1mo": 12,
}


def _net_pnl_for_run(result: RunResult) -> float:
    summary = result.summary
    if summary is None:
        return 0.0
    if summary.trade_diagnostics is not None:
        return summary.trade_diagnostics.net_pnl
    return summary.end_value - summary.start_value


def downsample_equity_curve(curve: list[EquityPoint], max_points: int = MAX_EQUITY_CURVE_POINTS) -> list[EquityPoint]:
    if len(curve) <= max_points:
        return curve
    if max_points < 2:
        return curve[:1]

    stride = max(1, math.ceil((len(curve) - 2) / (max_points - 2)))
    sampled = [curve[0]]
    index = stride
    while index < len(curve) - 1:
        sampled.append(curve[index])
        index += stride
    if sampled[-1] is not curve[-1]:
        sampled.append(curve[-1])
    return sampled


def merge_equity_curves(curves: list[list[EquityPoint]]) -> list[EquityPoint]:
    non_empty = [curve for curve in curves if curve]
    if not non_empty:
        return []
    if len(non_empty) == 1:
        return list(non_empty[0])

    all_timestamps: set[str] = set()
    for curve in non_empty:
        for point in curve:
            all_timestamps.add(point.datetime)
    ordered = sorted(all_timestamps)

    last_values = [curve[0].value for curve in non_empty]
    merged: list[EquityPoint] = []
    curve_indices = [0] * len(non_empty)

    for timestamp in ordered:
        combined = 0.0
        for idx, curve in enumerate(non_empty):
            while curve_indices[idx] < len(curve) and curve[curve_indices[idx]].datetime <= timestamp:
                last_values[idx] = curve[curve_indices[idx]].value
                curve_indices[idx] += 1
            combined += last_values[idx]
        merged.append(EquityPoint(datetime=timestamp, value=combined))
    return merged


def _max_drawdown_pct(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    peak = values[0]
    max_drawdown = 0.0
    for value in values:
        if value > peak:
            peak = value
        if peak > 0:
            drawdown = (peak - value) / peak * 100.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
    return max_drawdown if max_drawdown > 0 else 0.0


def _sharpe_from_equity(values: list[float], *, bars_per_year: float) -> float | None:
    if len(values) < 3 or bars_per_year <= 0:
        return None
    returns: list[float] = []
    for left, right in zip(values, values[1:]):
        if left > 0:
            returns.append((right - left) / left)
    if len(returns) < 2:
        return None
    avg_return = mean(returns)
    variance = sum((value - avg_return) ** 2 for value in returns) / (len(returns) - 1)
    if variance <= 0:
        return None
    std_dev = math.sqrt(variance)
    if std_dev == 0:
        return None
    return (avg_return / std_dev) * math.sqrt(bars_per_year)


def _infer_bars_per_year(results: list[RunResult]) -> float:
    for result in results:
        resolution = result.analyzers.get("resolution")
        if isinstance(resolution, str) and resolution in _BARS_PER_YEAR:
            return _BARS_PER_YEAR[resolution]
    return _BARS_PER_YEAR["1d"]


def compute_equity_metrics(
    curve: list[EquityPoint],
    *,
    start_value: float,
    bars_per_year: float,
) -> tuple[float | None, float | None]:
    if not curve:
        return None, None
    values = [point.value for point in curve]
    max_drawdown_pct = _max_drawdown_pct(values)
    sharpe_ratio = _sharpe_from_equity(values, bars_per_year=bars_per_year)
    if start_value > 0 and len(values) >= 1:
        _ = (values[-1] - start_value) / start_value * 100.0
    return max_drawdown_pct, sharpe_ratio


def _aggregate_strategy_runs(strategy: str, runs: list[RunResult]) -> StrategyAggregate:
    successful = [run for run in runs if run.status == "success" and run.summary is not None]
    failed = [run for run in runs if run.status == "failed"]

    symbols = sorted({run.symbol for run in runs if run.symbol})
    run_ids = [run.run_id for run in runs]

    if not successful:
        empty_summary = RunSummary(start_value=0.0, end_value=0.0, return_pct=0.0)
        return StrategyAggregate(
            strategy=strategy,
            symbols=symbols,
            run_ids=run_ids,
            successful_runs=0,
            failed_runs=len(failed),
            summary=empty_summary,
            equity_curve=[],
        )

    start_value = sum(run.summary.start_value for run in successful if run.summary)
    end_value = sum(run.summary.end_value for run in successful if run.summary)
    return_pct = ((end_value - start_value) / start_value * 100.0) if start_value else 0.0

    total_trades = sum(run.summary.total_trades for run in successful if run.summary)
    won_trades = sum(run.summary.won_trades for run in successful if run.summary)
    lost_trades = sum(run.summary.lost_trades for run in successful if run.summary)

    trades: list[TradeRecord] = []
    orders: list[OrderRecord] = []
    rejections: list[RejectionRecord] = []
    for run in successful:
        trades.extend(run.trades)
        orders.extend(run.orders)
        rejections.extend(run.rejections)

    trade_diagnostics = compute_trade_diagnostics(
        trades,
        orders,
        start_value=start_value,
        end_value=end_value,
    )
    filter_diagnostics = compute_filter_diagnostics(rejections, total_trades=total_trades)

    equity_curves = [run.equity_curve for run in successful if run.equity_curve]
    merged_curve = merge_equity_curves(equity_curves)
    bars_per_year = _infer_bars_per_year(successful)
    max_drawdown_pct, sharpe_ratio = compute_equity_metrics(
        merged_curve,
        start_value=start_value,
        bars_per_year=bars_per_year,
    )

    stored_curve = downsample_equity_curve(merged_curve) if merged_curve else []

    summary = RunSummary(
        start_value=start_value,
        end_value=end_value,
        return_pct=return_pct,
        max_drawdown_pct=max_drawdown_pct,
        sharpe_ratio=sharpe_ratio,
        total_trades=total_trades,
        won_trades=won_trades,
        lost_trades=lost_trades,
        trade_diagnostics=trade_diagnostics,
        filter_diagnostics=filter_diagnostics,
        risk_metrics=None,
    )

    return StrategyAggregate(
        strategy=strategy,
        symbols=symbols,
        run_ids=run_ids,
        successful_runs=len(successful),
        failed_runs=len(failed),
        summary=summary,
        equity_curve=stored_curve,
    )


def _compute_portfolio_aggregate(results: list[RunResult]) -> PortfolioAggregate | None:
    successful = [result for result in results if result.status == "success" and result.summary]
    if len(successful) <= 1:
        return None

    total_net_pnl = sum(_net_pnl_for_run(result) for result in successful)
    total_trades = sum(result.summary.total_trades for result in successful if result.summary)
    won_trades = sum(result.summary.won_trades for result in successful if result.summary)
    lost_trades = sum(result.summary.lost_trades for result in successful if result.summary)

    start_value = sum(result.summary.start_value for result in successful if result.summary)
    end_value = sum(result.summary.end_value for result in successful if result.summary)
    combined_return_pct = ((end_value - start_value) / start_value * 100.0) if start_value else None

    best_run_id: str | None = None
    worst_run_id: str | None = None
    best_return: float | None = None
    worst_return: float | None = None
    for result in successful:
        summary = result.summary
        if summary is None:
            continue
        if best_return is None or summary.return_pct > best_return:
            best_return = summary.return_pct
            best_run_id = result.run_id
        if worst_return is None or summary.return_pct < worst_return:
            worst_return = summary.return_pct
            worst_run_id = result.run_id

    return PortfolioAggregate(
        total_net_pnl=total_net_pnl,
        total_trades=total_trades,
        won_trades=won_trades,
        lost_trades=lost_trades,
        win_rate_pct=(won_trades / total_trades * 100.0) if total_trades else None,
        combined_return_pct=combined_return_pct,
        best_run_id=best_run_id,
        worst_run_id=worst_run_id,
    )


def compute_report_aggregates(results: list[RunResult]) -> ReportAggregates:
    by_strategy_name: dict[str, list[RunResult]] = defaultdict(list)
    for result in results:
        by_strategy_name[result.strategy].append(result)

    strategy_aggregates = [
        _aggregate_strategy_runs(strategy, runs)
        for strategy, runs in sorted(by_strategy_name.items())
    ]
    portfolio = _compute_portfolio_aggregate(results)

    return ReportAggregates(portfolio=portfolio, by_strategy=strategy_aggregates)
