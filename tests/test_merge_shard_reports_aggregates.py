from __future__ import annotations

from datetime import datetime, timezone

from app.backtests.merge import merge_shard_reports
from app.backtests.sharding import ShardPlan, ShardSpec
from app.output.models import BacktestReport, EquityPoint, RunResult, RunSummary


def _equity_curve(base: float, deltas: list[float], prefix: str) -> list[EquityPoint]:
    value = base
    points: list[EquityPoint] = [EquityPoint(datetime=f"{prefix}-01T00:00:00", value=value)]
    for idx, delta in enumerate(deltas, start=2):
        value += delta
        points.append(EquityPoint(datetime=f"{prefix}-{idx:02d}T00:00:00", value=value))
    return points


def test_merge_shard_reports_includes_aggregates(tmp_path):
    shard_a = tmp_path / "shard-a.json"
    shard_b = tmp_path / "shard-b.json"

    results_a = [
        RunResult(
            run_id="run-aapl",
            status="success",
            strategy="buy_and_hold",
            symbol="AAPL",
            data_source="yahoo",
            summary=RunSummary(
                start_value=10000.0,
                end_value=10200.0,
                return_pct=2.0,
                total_trades=1,
                won_trades=1,
                lost_trades=0,
            ),
            equity_curve=_equity_curve(10000.0, [200.0], prefix="2024-01"),
            analyzers={"resolution": "1d"},
        )
    ]
    results_b = [
        RunResult(
            run_id="run-msft",
            status="success",
            strategy="buy_and_hold",
            symbol="MSFT",
            data_source="yahoo",
            summary=RunSummary(
                start_value=10000.0,
                end_value=9800.0,
                return_pct=-2.0,
                total_trades=1,
                won_trades=0,
                lost_trades=1,
            ),
            equity_curve=_equity_curve(10000.0, [-200.0], prefix="2024-01"),
            analyzers={"resolution": "1d"},
        )
    ]

    shard_a.write_text(
        BacktestReport(
            generated_at=datetime.now(timezone.utc),
            app_version="0.0.0-test",
            config_sha256="abc",
            input_config_path=str(tmp_path / "config.yaml"),
            input_config={},
            total_runs=len(results_a),
            successful_runs=len(results_a),
            failed_runs=0,
            status="success",
            results=results_a,
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    shard_b.write_text(
        BacktestReport(
            generated_at=datetime.now(timezone.utc),
            app_version="0.0.0-test",
            config_sha256="abc",
            input_config_path=str(tmp_path / "config.yaml"),
            input_config={},
            total_runs=len(results_b),
            successful_runs=len(results_b),
            failed_runs=0,
            status="success",
            results=results_b,
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    plan = ShardPlan(
        config_path=str(tmp_path / "config.yaml"),
        split_by="symbol",
        shards=[
            ShardSpec(shard_id="a", config_path=str(tmp_path / "a.yaml"), output_path=str(shard_a)),
            ShardSpec(shard_id="b", config_path=str(tmp_path / "b.yaml"), output_path=str(shard_b)),
        ],
    )

    merged = merge_shard_reports(plan, original_config_raw={}, input_config_path=str(tmp_path / "config.yaml"))
    assert merged.aggregates is not None
    assert merged.aggregates.by_strategy
    strategy = merged.aggregates.by_strategy[0]
    assert strategy.strategy == "buy_and_hold"
    assert strategy.equity_curve
    assert strategy.summary.max_drawdown_pct is not None
    # Sharpe ratio can be null when the merged equity curve has zero variance.
    assert strategy.summary.sharpe_ratio is None or isinstance(strategy.summary.sharpe_ratio, float)
