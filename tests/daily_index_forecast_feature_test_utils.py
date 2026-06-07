from __future__ import annotations

from datetime import UTC, date, datetime, time
from typing import Iterable, Sequence
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from pandas.tseries.offsets import BDay

from app.config.models import CsvDataSource, DataCacheConfig
from app.daily_index_forecast.features import NY_TZ
from app.daily_index_forecast.models import (
    DailyIndexCostConfig,
    DailyIndexFeatureConfig,
    DailyIndexSeriesSpec,
    DailyIndexUniverseConfig,
)
from app.daily_index_forecast.records import DailyIndexFeatureRecord, DailyIndexLabelRecord


_NY = ZoneInfo(NY_TZ)


def make_business_days(start: str, count: int) -> list[date]:
    return [ts.date() for ts in pd.date_range(start, periods=count, freq=BDay())]


def make_daily_index_universe(
    *,
    start_date: date,
    end_date: date,
    symbol: str = "SPY",
    benchmark_symbol: str = "QQQ",
    decision_times: Sequence[str] = ("09:45",),
) -> DailyIndexUniverseConfig:
    return DailyIndexUniverseConfig(
        start_date=start_date,
        end_date=end_date,
        decision_times=list(decision_times),
        symbols=[
            DailyIndexSeriesSpec(
                symbol=symbol,
                data=CsvDataSource(type="csv", path="unused-symbol.csv"),
            )
        ],
        benchmark=DailyIndexSeriesSpec(
            symbol=benchmark_symbol,
            data=CsvDataSource(type="csv", path="unused-benchmark.csv"),
        ),
    )


def make_feature_config() -> DailyIndexFeatureConfig:
    return DailyIndexFeatureConfig(
        opening_window_minutes=15,
        rolling_sessions=[5, 20],
        benchmark_sessions=[5, 20],
        use_calendar_features=True,
        use_cross_market_features=True,
    )


def make_cost_config() -> DailyIndexCostConfig:
    return DailyIndexCostConfig(spread_bps=1.5, slippage_bps=1.0, impact_bps=0.5)


def make_data_cache(tmp_path: str | None = None) -> DataCacheConfig:
    return DataCacheConfig(directory=tmp_path or ".cache/daily-index-tests")


def _bar_timestamp(session_day: date, hour: int, minute: int) -> pd.Timestamp:
    local = pd.Timestamp.combine(session_day, time(hour, minute)).tz_localize(_NY)
    return local.tz_convert("UTC")


def make_session_frame(
    *,
    session_day: date,
    day_index: int,
    base_price: float,
    bar_minutes: Sequence[int] = (30, 35, 40, 45, 50),
) -> pd.DataFrame:
    rows: list[dict[str, float]] = []
    index: list[pd.Timestamp] = []
    for bar_index, minute in enumerate(bar_minutes):
        open_price = base_price + day_index * 1.25 + bar_index * 0.35
        close_price = open_price + 0.18 + day_index * 0.04 + bar_index * 0.02
        high_price = max(open_price, close_price) + 0.07 + bar_index * 0.01
        low_price = min(open_price, close_price) - 0.06
        volume = 1_000 + day_index * 120 + bar_index * 17
        rows.append(
            {
                "Open": open_price,
                "High": high_price,
                "Low": low_price,
                "Close": close_price,
                "Volume": volume,
            }
        )
        index.append(_bar_timestamp(session_day, 9, minute))
    return pd.DataFrame(rows, index=index)


def make_universe_frames(
    *,
    session_count: int = 25,
    start: str = "2024-01-02",
    symbol_base: float = 100.0,
    benchmark_base: float = 200.0,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, list[date]]:
    session_days = make_business_days(start, session_count)
    symbol_frames = [make_session_frame(session_day=day, day_index=i, base_price=symbol_base) for i, day in enumerate(session_days)]
    benchmark_frames = [
        make_session_frame(session_day=day, day_index=i, base_price=benchmark_base, bar_minutes=(30, 35, 40, 45, 50))
        for i, day in enumerate(session_days)
    ]
    symbol_frame = pd.concat(symbol_frames).sort_index()
    benchmark_frame = pd.concat(benchmark_frames).sort_index()
    return {"SPY": symbol_frame}, benchmark_frame, session_days


def make_minimal_no_future_frames() -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    session_day = date(2024, 1, 2)
    symbol_frame = pd.DataFrame(
        [
            {"Open": 100.0, "High": 100.2, "Low": 99.9, "Close": 100.1, "Volume": 1_000.0},
            {"Open": 100.1, "High": 100.3, "Low": 99.95, "Close": 100.2, "Volume": 1_020.0},
        ],
        index=[_bar_timestamp(session_day, 9, 30), _bar_timestamp(session_day, 9, 45)],
    )
    benchmark_frame = symbol_frame.rename(columns={col: col for col in symbol_frame.columns})
    benchmark_frame = benchmark_frame.copy()
    benchmark_frame[["Open", "High", "Low", "Close"]] = benchmark_frame[["Open", "High", "Low", "Close"]] + 100.0
    return {"SPY": symbol_frame}, benchmark_frame


def mutate_future_bars(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
    *,
    close_delta: float = 50.0,
    high_delta: float = 60.0,
    low_delta: float = 40.0,
    volume_delta: float = 5_000.0,
) -> pd.DataFrame:
    mutated = frame.copy()
    future_mask = mutated.index > cutoff
    mutated.loc[future_mask, "Close"] = mutated.loc[future_mask, "Close"].astype(float) + close_delta
    mutated.loc[future_mask, "High"] = mutated.loc[future_mask, "High"].astype(float) + high_delta
    mutated.loc[future_mask, "Low"] = mutated.loc[future_mask, "Low"].astype(float) - low_delta
    mutated.loc[future_mask, "Volume"] = mutated.loc[future_mask, "Volume"].astype(float) + volume_delta
    return mutated


def session_summaries(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    rows: list[dict[str, float | date]] = []
    for session_day in sorted({ts.tz_convert(_NY).date() for ts in frame.index}):
        session_mask = frame.index.map(lambda ts: ts.tz_convert(_NY).date()) == session_day
        session = frame.loc[session_mask].sort_index()
        if session.empty:
            continue
        open_price = float(session["Open"].iloc[0])
        close_price = float(session["Close"].iloc[-1])
        high_price = float(session["High"].max())
        low_price = float(session["Low"].min())
        volume = float(session["Volume"].sum())
        prev_close = float(session["Close"].iloc[-2]) if len(session) > 1 else close_price
        rows.append(
            {
                "session_date": session_day,
                "open_price": open_price,
                "close_price": close_price,
                "high_price": high_price,
                "low_price": low_price,
                "volume": volume,
                "session_return_pct": (close_price / open_price - 1.0) if open_price else None,
                "session_close_return_pct": (close_price / prev_close - 1.0) if prev_close else None,
                "session_range_pct": ((high_price - low_price) / open_price) if open_price else None,
            }
        )
    return pd.DataFrame(rows).sort_values("session_date").reset_index(drop=True)


def compound_return(returns: Sequence[float | None]) -> float | None:
    values = [float(value) for value in returns if value is not None]
    if len(values) < len(returns):
        return None
    return float(np.prod(1.0 + np.asarray(values, dtype=float)) - 1.0)


def rolling_std(values: Sequence[float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if len(filtered) < len(values):
        return None
    return float(np.std(np.asarray(filtered, dtype=float), ddof=0))


def zscore_last(values: Sequence[float | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if len(filtered) < len(values) or len(filtered) < 2:
        return None
    series = np.asarray(filtered, dtype=float)
    std = float(series.std(ddof=0))
    if std == 0:
        return None
    return float((series[-1] - series.mean()) / std)


def select_feature_record(
    records: Sequence[DailyIndexFeatureRecord],
    *,
    symbol: str,
    session_date: date,
    decision_time: str,
) -> DailyIndexFeatureRecord:
    for record in records:
        if record.symbol == symbol and record.session_date == session_date and record.decision_time == decision_time:
            return record
    raise AssertionError(f"Feature record not found for {symbol} {session_date} {decision_time}")


def select_label_record(
    records: Sequence[DailyIndexLabelRecord],
    *,
    symbol: str,
    session_date: date,
    decision_time: str,
) -> DailyIndexLabelRecord:
    for record in records:
        if record.symbol == symbol and record.session_date == session_date and record.decision_time == decision_time:
            return record
    raise AssertionError(f"Label record not found for {symbol} {session_date} {decision_time}")


def assert_fields_equal(left: object, right: object, fields: Iterable[str]) -> None:
    for field in fields:
        left_value = getattr(left, field)
        right_value = getattr(right, field)
        assert left_value == right_value, f"field {field!r} differed: {left_value!r} != {right_value!r}"
