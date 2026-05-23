from __future__ import annotations

from datetime import timedelta

import pandas as pd

from app.data.cache import CacheKey, ParquetDataCache


def test_cache_key_deterministic():
    k1 = CacheKey(
        source="yahoo",
        symbol="aapl",
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )
    k2 = CacheKey(
        source="yahoo",
        symbol="AAPL",
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-10",
    )
    assert k1.stable_id() == k2.stable_id()


def test_cache_path_generation(tmp_path):
    cache = ParquetDataCache(tmp_path)
    key = CacheKey(
        source="yahoo",
        symbol="AAPL",
        interval="1h",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )
    path = cache.path_for(key)
    assert path.suffix == ".parquet"
    assert "yahoo" in str(path)
    assert "AAPL" in str(path)
    assert "1h" in str(path)


def test_cache_ttl_hit_and_stale(tmp_path):
    cache = ParquetDataCache(tmp_path)
    key = CacheKey(
        source="yahoo",
        symbol="AAPL",
        interval="1d",
        start_date="2024-01-01",
        end_date="2024-01-31",
    )
    frame = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [100]},
        index=pd.to_datetime(["2024-01-01"]),
    )
    path = cache.put(key, frame)

    hit = cache.get(key, max_age=timedelta(days=1))
    assert hit.status == "hit"
    assert hit.frame is not None

    old_ts = path.stat().st_mtime - 3 * 24 * 60 * 60
    path.touch()
    import os

    os.utime(path, (old_ts, old_ts))

    stale = cache.get(key, max_age=timedelta(hours=1))
    assert stale.status == "stale_refetch"
    assert stale.frame is None

