from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from app.scans.momentum_scanner import run_momentum_scan
from app.scans.params import MomentumScanParams


def _frame_from_closes(closes: list[float], *, volumes: list[int] | None = None) -> pd.DataFrame:
    if volumes is None:
        volumes = [1_000_000 for _ in closes]
    index = pd.date_range("2024-01-01", periods=len(closes), freq="D", tz="UTC")
    df = pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
            "Volume": volumes,
        },
        index=index,
    )
    return df


def test_momentum_scan_prefilter_rejects_low_price_and_liquidity() -> None:
    params = MomentumScanParams(
        symbols=["AAA", "BBB"],
        lookback_days=30,
        min_avg_dollar_volume=5_000_000,
        min_price=5.0,
        max_symbols=100,
    )

    short_frames = {
        "AAA": _frame_from_closes([10.0] * 30, volumes=[1_000_000] * 30),  # avg DV = 10M pass
        "BBB": _frame_from_closes([4.0] * 30, volumes=[1_000_000] * 30),  # fails min_price
    }

    def fetch_short(symbol: str, days: int) -> pd.DataFrame:
        return short_frames[symbol].tail(days)

    def fetch_full(symbol: str, days: int) -> pd.DataFrame:
        # Provide enough bars for features.
        return _frame_from_closes(list(range(1, 1 + max(days, 260))), volumes=[1_000_000] * max(days, 260))

    output = run_momentum_scan(
        params,
        as_of=datetime(2026, 5, 31, tzinfo=timezone.utc),
        fetch_short=fetch_short,
        fetch_full=fetch_full,
    )

    assert [r.symbol for r in output.results] == ["AAA"]
    excluded = {(x.symbol, x.reason) for x in output.excluded}
    assert ("BBB", "below_min_price") in excluded


def test_momentum_scan_two_stage_fetches_full_only_for_survivors(tmp_path: Path) -> None:
    params = MomentumScanParams(
        symbols=["AAA", "BBB", "CCC"],
        lookback_days=30,
        min_avg_dollar_volume=5_000_000,
        min_price=5.0,
        max_symbols=100,
    )

    # AAA passes, BBB fails liquidity, CCC fails price.
    short_frames = {
        "AAA": _frame_from_closes([10.0] * 30, volumes=[1_000_000] * 30),  # 10M pass
        "BBB": _frame_from_closes([10.0] * 30, volumes=[10_000] * 30),  # 100k fail
        "CCC": _frame_from_closes([4.0] * 30, volumes=[1_000_000] * 30),  # price fail
    }

    short_calls: list[str] = []
    full_calls: list[str] = []

    def fetch_short(symbol: str, days: int) -> pd.DataFrame:
        short_calls.append(symbol)
        return short_frames[symbol].tail(days)

    def fetch_full(symbol: str, days: int) -> pd.DataFrame:
        full_calls.append(symbol)
        closes = [10.0 + i * 0.1 for i in range(max(days, 260))]
        return _frame_from_closes(closes, volumes=[1_000_000] * len(closes))

    output = run_momentum_scan(
        params,
        as_of=datetime(2026, 5, 31, tzinfo=timezone.utc),
        fetch_short=fetch_short,
        fetch_full=fetch_full,
    )

    assert set(short_calls) == {"AAA", "BBB", "CCC"}
    assert full_calls == ["AAA"]
    assert [r.symbol for r in output.results] == ["AAA"]
    excluded = {(x.symbol, x.reason) for x in output.excluded}
    assert ("BBB", "low_avg_dollar_volume_20d") in excluded
    assert ("CCC", "below_min_price") in excluded

