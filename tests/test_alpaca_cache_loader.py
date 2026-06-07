from __future__ import annotations

import json
from datetime import date
from urllib.parse import urlparse, parse_qs

import pytest

from app.config.models import AlpacaDataSource, AlpacaOptionsDataSource, DataCacheConfig
from app.data.loaders import build_alpaca_data_feed_with_cache
from app.data.loaders import build_alpaca_options_data_feed_with_cache


def _mock_alpaca_payload() -> bytes:
    payload = {
        "bars": [
            {"t": "2024-01-01T00:00:00Z", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 1000},
            {"t": "2024-01-02T00:00:00Z", "o": 101.0, "h": 102.0, "l": 100.0, "c": 101.5, "v": 1100},
        ],
        "next_page_token": None,
    }
    return json.dumps(payload).encode("utf-8")


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False


def test_alpaca_cache_miss_then_hit(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        return _FakeResponse(_mock_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)

    config = AlpacaDataSource(type="alpaca", symbol="AAPL", interval="1d")
    cache_cfg = DataCacheConfig(directory=str(tmp_path))

    _, s1 = build_alpaca_data_feed_with_cache(
        config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )
    _, s2 = build_alpaca_data_feed_with_cache(
        config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )

    assert calls["n"] == 1
    assert s1 == "miss"
    assert s2 == "hit"


def test_alpaca_different_feeds_use_separate_cache_entries(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        return _FakeResponse(_mock_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)

    cache_cfg = DataCacheConfig(directory=str(tmp_path))
    iex = AlpacaDataSource(type="alpaca", symbol="AAPL", interval="1d", feed="iex")
    sip = AlpacaDataSource(type="alpaca", symbol="AAPL", interval="1d", feed="sip")

    build_alpaca_data_feed_with_cache(
        iex, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )
    build_alpaca_data_feed_with_cache(
        sip, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
    )

    assert calls["n"] == 2


def test_alpaca_null_bars_returns_clear_error(tmp_path, monkeypatch):
    def fake_urlopen(*args, **kwargs):
        return _FakeResponse(json.dumps({"bars": None, "next_page_token": None}).encode("utf-8"))

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)

    config = AlpacaDataSource(type="alpaca", symbol="AAPL", interval="1m")
    cache_cfg = DataCacheConfig(directory=str(tmp_path), enabled=False)

    with pytest.raises(RuntimeError) as exc:
        build_alpaca_data_feed_with_cache(
            config, date(2026, 5, 24), date(2026, 5, 24), cache_cfg, force_refresh=False
        )
    assert "No Alpaca data found" in str(exc.value)


def test_alpaca_requires_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    config = AlpacaDataSource(type="alpaca", symbol="AAPL", interval="1d")
    cache_cfg = DataCacheConfig(directory=str(tmp_path))

    with pytest.raises(RuntimeError) as exc:
        build_alpaca_data_feed_with_cache(
            config, date(2024, 1, 1), date(2024, 1, 3), cache_cfg, force_refresh=False
        )
    assert "Alpaca credentials missing" in str(exc.value)


def test_alpaca_request_includes_full_stop_day(tmp_path, monkeypatch):
    captured_urls: list[str] = []

    def fake_urlopen(request, *args, **kwargs):
        captured_urls.append(request.full_url)
        return _FakeResponse(_mock_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)

    config = AlpacaDataSource(type="alpaca", symbol="AAPL", interval="1m")
    cache_cfg = DataCacheConfig(directory=str(tmp_path), enabled=False)

    build_alpaca_data_feed_with_cache(
        config, date(2024, 1, 15), date(2024, 1, 15), cache_cfg, force_refresh=False
    )

    assert captured_urls
    assert "start=2024-01-15T00%3A00%3A00Z" in captured_urls[0]
    assert "end=2024-01-16T00%3A00%3A00Z" in captured_urls[0]


def test_alpaca_options_requests_include_requested_feed(tmp_path, monkeypatch):
    captured_urls: list[str] = []

    def fake_urlopen(request, *args, **kwargs):
        captured_urls.append(request.full_url)
        if "snapshots" in request.full_url:
            payload = {
                "snapshots": {
                    "AAPL240621C00100000": {
                        "symbol": "AAPL240621C00100000",
                    }
                }
            }
        else:
            payload = {
                "bars": [
                    {
                        "t": "2024-01-01T00:00:00Z",
                        "o": 1.0,
                        "h": 1.0,
                        "l": 1.0,
                        "c": 1.0,
                        "v": 1,
                    }
                ],
                "next_page_token": None,
            }
        return _FakeResponse(json.dumps(payload).encode("utf-8"))

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)

    config = AlpacaOptionsDataSource(type="alpaca-options", symbol="AAPL", interval="1d", feed="indicative")
    cache_cfg = DataCacheConfig(directory=str(tmp_path), enabled=False)

    build_alpaca_options_data_feed_with_cache(
        config,
        date(2024, 1, 1),
        date(2024, 1, 3),
        cache_cfg,
        force_refresh=False,
    )

    assert len(captured_urls) == 2
    snapshot_query = parse_qs(urlparse(captured_urls[0]).query)
    bars_query = parse_qs(urlparse(captured_urls[1]).query)
    assert snapshot_query["feed"] == ["indicative"]
    assert bars_query["feed"] == ["indicative"]
