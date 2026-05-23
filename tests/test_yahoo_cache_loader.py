from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from app.config.models import DataCacheConfig, YahooDataSource
from app.data.loaders import build_yahoo_data_feed_with_cache


def _fake_df():
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.5, 101.5],
            "Volume": [1000, 1100],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )


def test_yahoo_cache_miss_then_hit(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_download(*args, **kwargs):
        calls["n"] += 1
        return _fake_df()

    fake_yf = SimpleNamespace(download=fake_download)
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_yf)

    config = YahooDataSource(type="yahoo", symbol="AAPL", interval="1d")
    cache_cfg = DataCacheConfig(directory=str(tmp_path))

    _, s1 = build_yahoo_data_feed_with_cache(
        config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )
    _, s2 = build_yahoo_data_feed_with_cache(
        config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )

    assert calls["n"] == 1
    assert s1 == "miss"
    assert s2 == "hit"


def test_yahoo_cache_force_refresh(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_download(*args, **kwargs):
        calls["n"] += 1
        return _fake_df()

    fake_yf = SimpleNamespace(download=fake_download)
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_yf)

    config = YahooDataSource(type="yahoo", symbol="AAPL", interval="1d")
    cache_cfg = DataCacheConfig(directory=str(tmp_path))

    build_yahoo_data_feed_with_cache(
        config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )
    _, status = build_yahoo_data_feed_with_cache(
        config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=True
    )
    assert calls["n"] == 2
    assert status == "force_refresh"


def test_yahoo_cache_disabled(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_download(*args, **kwargs):
        calls["n"] += 1
        return _fake_df()

    fake_yf = SimpleNamespace(download=fake_download)
    monkeypatch.setitem(__import__("sys").modules, "yfinance", fake_yf)

    config = YahooDataSource(type="yahoo", symbol="AAPL", interval="1d")
    cache_cfg = DataCacheConfig(enabled=False, directory=str(tmp_path))

    _, s1 = build_yahoo_data_feed_with_cache(
        config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )
    _, s2 = build_yahoo_data_feed_with_cache(
        config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )
    assert calls["n"] == 2
    assert s1 == "miss"
    assert s2 == "miss"

