from __future__ import annotations

from datetime import date
from pathlib import Path

from app.datasets.sharding import build_dataset_shard_plan, estimate_dataset_shard_count


def test_estimate_dataset_shard_count_scales_with_job_shape() -> None:
    small = estimate_dataset_shard_count(
        symbol_count=1,
        resolution="1d",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 1),
        options_enabled=False,
        max_shards=5,
        target_work_units=1_000,
    )
    medium = estimate_dataset_shard_count(
        symbol_count=4,
        resolution="1m",
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 10),
        options_enabled=False,
        max_shards=5,
        target_work_units=1_000,
    )
    large = estimate_dataset_shard_count(
        symbol_count=20,
        resolution="1m",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        options_enabled=True,
        max_shards=5,
        target_work_units=1_000,
    )

    assert small == 1
    assert medium > small
    assert large == 5


def test_build_dataset_shard_plan_caps_shards_and_parallelism(tmp_path: Path) -> None:
    plan = build_dataset_shard_plan(
        dataset_id="ds-1",
        symbols=["aapl", "msft", "qqq", "spy", "tsla", "nvda", "meta", "amd"],
        provider="alpaca",
        resolution="1m",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 31),
        options_enabled=True,
        options_feed="indicative",
        output_dir=tmp_path,
        max_shards=3,
        max_pods=2,
        target_work_units=1_000,
    )

    assert plan.shard_count == 3
    assert plan.parallelism == 2
    assert len(plan.shards) == 3
    assert plan.shards[0].symbols_csv
    assert plan.shards[0].work_units > 0


def test_build_dataset_shard_plan_is_deterministic(tmp_path: Path) -> None:
    plan = build_dataset_shard_plan(
        dataset_id="ds-2",
        symbols=["MSFT", "AAPL", "QQQ", "MSFT"],
        provider="alpaca",
        resolution="5m",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 3),
        options_enabled=False,
        options_feed="indicative",
        output_dir=tmp_path,
        max_shards=4,
        max_pods=4,
        target_work_units=1_000,
    )

    assert plan.symbols == ["MSFT", "AAPL", "QQQ"]
    assert plan.shards[0].symbols_csv
    assert all(shard.shard_id.startswith("shard-") for shard in plan.shards)


def test_build_dataset_shard_plan_caps_symbols_per_shard(tmp_path: Path) -> None:
    plan = build_dataset_shard_plan(
        dataset_id="ds-3",
        symbols=["AAPL", "MSFT", "QQQ", "SPY", "TSLA"],
        provider="alpaca",
        resolution="1m",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 1, 2),
        options_enabled=False,
        options_feed="indicative",
        output_dir=tmp_path,
        max_shards=5,
        max_pods=4,
        target_work_units=10_000,
        max_symbols_per_shard=2,
    )

    assert plan.shard_count == 3
    assert plan.max_symbols_per_shard == 2
    assert all(shard.symbol_count <= 2 for shard in plan.shards)


def test_build_dataset_shard_plan_errors_when_symbol_cap_needs_more_shards_than_allowed(tmp_path: Path) -> None:
    try:
        build_dataset_shard_plan(
            dataset_id="ds-4",
            symbols=["AAPL", "MSFT", "QQQ", "SPY", "TSLA"],
            provider="alpaca",
            resolution="1m",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
            options_enabled=False,
            options_feed="indicative",
            output_dir=tmp_path,
            max_shards=2,
            max_pods=2,
            target_work_units=10_000,
            max_symbols_per_shard=2,
        )
    except ValueError as exc:
        assert "Cannot satisfy max_symbols_per_shard" in str(exc)
    else:
        raise AssertionError("expected build_dataset_shard_plan to reject impossible symbol cap")
