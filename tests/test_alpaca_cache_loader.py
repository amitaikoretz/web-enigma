from __future__ import annotations

import json
from datetime import date

import pytest

from app.config.models import AlpacaDataSource, DataCacheConfig
from app.data.loaders import build_alpaca_data_feed_with_cache


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
