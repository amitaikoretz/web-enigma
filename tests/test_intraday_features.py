from __future__ import annotations

import numpy as np
import pandas as pd

from app.intraday.features import build_intraday_rows


def _frame(close_offset: float = 0.0) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=120, freq="D", tz="UTC")
    rows = []
    for i in range(len(index)):
        close = 100.0 + i * 0.25 + close_offset
        rows.append(
            {
                "Open": close - 0.2,
                "High": close + 0.4,
                "Low": close - 0.5,
                "Close": close,
                "Volume": 10_000 + i * 10,
            }
        )
    return pd.DataFrame(rows, index=index)


def test_intraday_features_are_point_in_time_safe() -> None:
    frame = _frame()
    benchmark = _frame(close_offset=1.0)
    rows_before = build_intraday_rows(frame, symbol="TEST", horizon_bars=5, benchmark_frame=benchmark, lookback_bars=20)
    assert rows_before

    target = rows_before[10]
    mutated = frame.copy()
    mutated.iloc[80:, mutated.columns.get_loc("Close")] = 999.0
    mutated.iloc[80:, mutated.columns.get_loc("High")] = 1000.0
    rows_after = build_intraday_rows(mutated, symbol="TEST", horizon_bars=5, benchmark_frame=benchmark, lookback_bars=20)
    assert rows_after

    same_row = next(row for row in rows_after if row.timestamp == target.timestamp)
    assert np.isclose(target.features["ret_20"], same_row.features["ret_20"])
    assert np.isclose(target.features["trend_slope_20"], same_row.features["trend_slope_20"])
    assert target.features["benchmark_ret_20"] == same_row.features["benchmark_ret_20"]


def test_intraday_features_skip_insufficient_history() -> None:
    frame = _frame().iloc[:15]
    rows = build_intraday_rows(frame, symbol="TEST", horizon_bars=5, benchmark_frame=None, lookback_bars=20)
    assert rows == []
