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

