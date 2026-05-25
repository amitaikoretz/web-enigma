from __future__ import annotations

from datetime import datetime, timezone

from app.engine.aggregates import (
    compute_equity_metrics,
    compute_report_aggregates,
    downsample_equity_curve,
    merge_equity_curves,
)
from app.output.models import (
    BacktestReport,
    EquityPoint,
    OrderRecord,
    RunResult,
    RunSummary,
    TradeRecord,
)


def _equity_curve(base: float, deltas: list[float], prefix: str = "2024-01") -> list[EquityPoint]:
    value = base
    points = [EquityPoint(datetime=f"{prefix}-0{idx + 1:02d}T00:00:00", value=value) for idx in range(1)]
    value = base
    for idx, delta in enumerate(deltas, start=2):
        value += delta
        points.append(EquityPoint(datetime=f"{prefix}-0{idx:02d}T00:00:00", value=value))
    return points


def test_merge_equity_curves_sums_aligned_values():
    curve_a = [
        EquityPoint(datetime="2024-01-01T00:00:00", value=10000.0),
        EquityPoint(datetime="2024-01-02T00:00:00", value=10100.0),
        EquityPoint(datetime="2024-01-03T00:00:00", value=10200.0),
    ]
    curve_b = [
        EquityPoint(datetime="2024-01-01T00:00:00", value=10000.0),
        EquityPoint(datetime="2024-01-03T00:00:00", value=9900.0),
    ]
    merged = merge_equity_curves([curve_a, curve_b])
    assert len(merged) == 3
    assert merged[0].value == 20000.0
    assert merged[1].value == 20100.0
    assert merged[2].value == 20100.0


def test_compute_equity_metrics_drawdown_and_sharpe():
    curve = _equity_curve(10000.0, [100.0, -250.0, 50.0, 200.0])
    max_dd, sharpe = compute_equity_metrics(curve, start_value=10000.0, bars_per_year=252)
    assert max_dd is not None
    assert max_dd > 0
    assert sharpe is not None


def test_downsample_equity_curve_keeps_endpoints():
    curve = [EquityPoint(datetime=f"2024-01-{idx:02d}T00:00:00", value=float(idx)) for idx in range(1, 5001)]
    sampled = downsample_equity_curve(curve, max_points=100)
    assert len(sampled) <= 100
    assert sampled[0].datetime == curve[0].datetime
    assert sampled[-1].datetime == curve[-1].datetime


def test_strategy_aggregate_sums_trades_and_diagnostics():
    trades_a = [
        TradeRecord(size=1, price=10, value=10, pnl=5, pnlcomm=4, reason="target"),
    ]
    trades_b = [
        TradeRecord(size=1, price=10, value=10, pnl=-2, pnlcomm=-3, reason="stop"),
    ]
    orders = [
        OrderRecord(status="Completed", is_buy=True, size=1, price=10, value=10, commission=1.0),
    ]
    results = [
        RunResult(
            run_id="run-aapl",
            status="success",
            strategy="volume_rally",
            symbol="AAPL",
            data_source="yahoo",
            summary=RunSummary(
                start_value=10000.0,
                end_value=10004.0,
                return_pct=0.04,
                total_trades=1,
                won_trades=1,
                lost_trades=0,
            ),
            trades=trades_a,
            orders=orders,
            equity_curve=_equity_curve(10000.0, [4.0]),
            analyzers={"resolution": "1d"},
        ),
        RunResult(
            run_id="run-msft",
            status="success",
            strategy="volume_rally",
            symbol="MSFT",
            data_source="yahoo",
            summary=RunSummary(
                start_value=10000.0,
                end_value=9997.0,
                return_pct=-0.03,
                total_trades=1,
                won_trades=0,
                lost_trades=1,
            ),
            trades=trades_b,
            orders=orders,
            equity_curve=_equity_curve(10000.0, [-3.0]),
            analyzers={"resolution": "1d"},
        ),
    ]

    aggregates = compute_report_aggregates(results)
    assert len(aggregates.by_strategy) == 1
    strategy = aggregates.by_strategy[0]
    assert strategy.strategy == "volume_rally"
    assert strategy.symbols == ["AAPL", "MSFT"]
    assert strategy.summary.total_trades == 2
    assert strategy.summary.won_trades == 1
    assert strategy.summary.lost_trades == 1
    assert strategy.summary.start_value == 20000.0
    assert strategy.summary.end_value == 20001.0
    assert strategy.summary.trade_diagnostics is not None
    assert strategy.summary.trade_diagnostics.net_pnl == 1.0
    assert strategy.equity_curve


def test_strategy_aggregate_null_risk_metrics_without_equity_curve():
    results = [
        RunResult(
            run_id="run-aapl",
            status="success",
            strategy="sma_cross",
            symbol="AAPL",
            data_source="yahoo",
            summary=RunSummary(start_value=10000.0, end_value=10100.0, return_pct=1.0, total_trades=2, won_trades=1, lost_trades=1),
        ),
        RunResult(
            run_id="run-msft",
            status="success",
            strategy="sma_cross",
            symbol="MSFT",
            data_source="yahoo",
            summary=RunSummary(start_value=10000.0, end_value=10050.0, return_pct=0.5, total_trades=1, won_trades=1, lost_trades=0),
        ),
    ]
    aggregates = compute_report_aggregates(results)
    strategy = aggregates.by_strategy[0]
    assert strategy.summary.max_drawdown_pct is None
    assert strategy.summary.sharpe_ratio is None
    assert strategy.equity_curve == []


def test_portfolio_aggregate_best_and_worst_runs():
    results = [
        RunResult(
            run_id="best",
            status="success",
            strategy="sma_cross",
            symbol="NVDA",
            data_source="yahoo",
            summary=RunSummary(start_value=10000.0, end_value=11800.0, return_pct=18.0, total_trades=5, won_trades=4, lost_trades=1),
        ),
        RunResult(
            run_id="worst",
            status="success",
            strategy="sma_cross",
            symbol="MSFT",
            data_source="yahoo",
            summary=RunSummary(start_value=10000.0, end_value=9700.0, return_pct=-3.0, total_trades=3, won_trades=1, lost_trades=2),
        ),
    ]
    aggregates = compute_report_aggregates(results)
    assert aggregates.portfolio is not None
    assert aggregates.portfolio.best_run_id == "best"
    assert aggregates.portfolio.worst_run_id == "worst"
    assert aggregates.portfolio.total_trades == 8
    assert aggregates.portfolio.combined_return_pct == 7.5


def test_backtest_report_json_includes_aggregates():
    results = [
        RunResult(
            run_id="run-aapl",
            status="success",
            strategy="buy_and_hold",
            symbol="AAPL",
            data_source="yahoo",
            summary=RunSummary(start_value=10000.0, end_value=10500.0, return_pct=5.0, total_trades=1, won_trades=1, lost_trades=0),
            equity_curve=_equity_curve(10000.0, [500.0]),
            analyzers={"resolution": "1d"},
        ),
        RunResult(
            run_id="run-msft",
            status="success",
            strategy="buy_and_hold",
            symbol="MSFT",
            data_source="yahoo",
            summary=RunSummary(start_value=10000.0, end_value=10300.0, return_pct=3.0, total_trades=1, won_trades=1, lost_trades=0),
            equity_curve=_equity_curve(10000.0, [300.0]),
            analyzers={"resolution": "1d"},
        ),
    ]
    report = BacktestReport(
        generated_at=datetime.now(timezone.utc),
        app_version="0.1.0",
        config_sha256="abc",
        total_runs=2,
        successful_runs=2,
        failed_runs=0,
        status="success",
        results=results,
        aggregates=compute_report_aggregates(results),
    )
    payload = report.model_dump(mode="json")
    assert payload["aggregates"]["by_strategy"]
    assert payload["aggregates"]["portfolio"]["best_run_id"] == "run-aapl"
