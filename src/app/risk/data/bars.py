from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from app.config.models import AlpacaDataSource, CsvDataSource, DataCacheConfig, YahooDataSource
from app.data.loaders import (
    build_alpaca_data_feed_with_cache,
    build_csv_data_feed,
    build_yahoo_data_feed_with_cache,
)
from app.risk.models import EnrichedCandidate


INTERVAL_DURATIONS: dict[str, timedelta] = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
}


def interval_duration(interval: str) -> timedelta:
    key = interval.lower()
    if key not in INTERVAL_DURATIONS:
        raise ValueError(f"Unsupported interval '{interval}'")
    return INTERVAL_DURATIONS[key]


def parse_timestamp(value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def bar_index_at_or_before(frame: pd.DataFrame, timestamp: str | pd.Timestamp) -> int | None:
    if frame.empty:
        return None
    ts = parse_timestamp(timestamp) if isinstance(timestamp, str) else timestamp
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    index = frame.index
    if index.tz is None:
        index = index.tz_localize("UTC")
    else:
        index = index.tz_convert("UTC")
    positions = index.searchsorted(ts, side="right") - 1
    if positions < 0:
        return None
    return int(positions)


def forward_bars(frame: pd.DataFrame, start_idx: int, count: int) -> pd.DataFrame:
    if start_idx < 0 or start_idx >= len(frame):
        return frame.iloc[0:0]
    end = min(len(frame), start_idx + count + 1)
    return frame.iloc[start_idx + 1 : end]


def history_bars(frame: pd.DataFrame, end_idx: int, count: int | None = None) -> pd.DataFrame:
    if end_idx < 0:
        return frame.iloc[0:0]
    if count is None:
        return frame.iloc[: end_idx + 1]
    start = max(0, end_idx + 1 - count)
    return frame.iloc[start : end_idx + 1]


@dataclass(frozen=True)
class BarGroupKey:
    symbol: str
    interval: str
    feed: str | None
    data_source: str
    csv_path: str | None


class BarStore:
    def __init__(
        self,
        *,
        cache_config: DataCacheConfig,
        cache_refresh: bool = False,
    ) -> None:
        self.cache_config = cache_config
        self.cache_refresh = cache_refresh
        self._frames: dict[BarGroupKey, pd.DataFrame] = {}

    def _load_frame(
        self,
        key: BarGroupKey,
        *,
        start_date: date,
        end_date: date,
        sample: EnrichedCandidate,
    ) -> pd.DataFrame:
        if key.data_source == "csv":
            if not key.csv_path:
                raise ValueError(f"CSV path missing for symbol {key.symbol}")
            return build_csv_data_feed(
                CsvDataSource(type="csv", path=key.csv_path),
                start_date,
                end_date,
            )
        if key.data_source == "yahoo":
            source = YahooDataSource(type="yahoo", symbol=key.symbol, interval=key.interval)
            frame, _ = build_yahoo_data_feed_with_cache(
                source,
                start_date,
                end_date,
                cache_config=self.cache_config,
                force_refresh=self.cache_refresh,
            )
            return frame
        if key.data_source == "alpaca":
            feed = key.feed or "iex"
            source = AlpacaDataSource(type="alpaca", symbol=key.symbol, interval=key.interval, feed=feed)  # type: ignore[arg-type]
            frame, _ = build_alpaca_data_feed_with_cache(
                source,
                start_date,
                end_date,
                cache_config=self.cache_config,
                force_refresh=self.cache_refresh,
            )
            return frame
        raise ValueError(f"Unsupported data source '{key.data_source}' for {key.symbol}")

    def prepare(self, candidates: list[EnrichedCandidate], *, lookback_bars: int) -> None:
        groups: dict[BarGroupKey, list[EnrichedCandidate]] = {}
        for candidate in candidates:
            interval = candidate.resolution or "1d"
            key = BarGroupKey(
                symbol=candidate.symbol,
                interval=interval,
                feed=candidate.feed,
                data_source=candidate.data_source,
                csv_path=candidate.csv_path,
            )
            groups.setdefault(key, []).append(candidate)

        for key, rows in groups.items():
            interval = key.interval
            duration = interval_duration(interval)
            timestamps = [parse_timestamp(row.timestamp) for row in rows]
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            max_horizon = max(row.planned_horizon_bars for row in rows)

            load_start_ts = min_ts - duration * lookback_bars
            load_end_ts = max_ts + duration * (max_horizon + 2)
            start_date = load_start_ts.date()
            end_date = load_end_ts.date()

            if rows[0].start_date and rows[0].start_date < start_date:
                start_date = rows[0].start_date
            if rows[0].end_date and rows[0].end_date > end_date:
                end_date = rows[0].end_date

            self._frames[key] = self._load_frame(key, start_date=start_date, end_date=end_date, sample=rows[0])

    def prepare_benchmarks(
        self,
        candidates: list[EnrichedCandidate],
        *,
        lookback_bars: int,
        default_symbol: str,
    ) -> dict[tuple[str, str, str | None], pd.DataFrame]:
        benchmark_frames: dict[tuple[str, str, str | None], pd.DataFrame] = {}
        by_key: dict[tuple[str, str, str | None, str], list[EnrichedCandidate]] = {}
        for candidate in candidates:
            symbol = candidate.benchmark_symbol or default_symbol
            if candidate.data_source == "csv":
                continue
            interval = candidate.resolution or "1d"
            feed = candidate.feed
            group = (symbol, interval, feed, candidate.data_source)
            by_key.setdefault(group, []).append(candidate)

        for (symbol, interval, feed, data_source), rows in by_key.items():
            duration = interval_duration(interval)
            timestamps = [parse_timestamp(row.timestamp) for row in rows]
            min_ts = min(timestamps)
            max_ts = max(timestamps)
            max_horizon = max(row.planned_horizon_bars for row in rows)
            start_date = (min_ts - duration * lookback_bars).date()
            end_date = (max_ts + duration * (max_horizon + 2)).date()

            key = BarGroupKey(symbol=symbol, interval=interval, feed=feed, data_source=data_source, csv_path=None)
            benchmark_frames[(symbol, interval, feed)] = self._load_frame(
                key,
                start_date=start_date,
                end_date=end_date,
                sample=rows[0],
            )
        return benchmark_frames

    def get_symbol_frame(self, candidate: EnrichedCandidate) -> pd.DataFrame:
        key = BarGroupKey(
            symbol=candidate.symbol,
            interval=candidate.resolution or "1d",
            feed=candidate.feed,
            data_source=candidate.data_source,
            csv_path=candidate.csv_path,
        )
        frame = self._frames.get(key)
        if frame is None:
            raise KeyError(f"No bars loaded for {key}")
        return frame

    def get_benchmark_frame(
        self,
        candidate: EnrichedCandidate,
        *,
        default_symbol: str,
        benchmark_frames: dict[tuple[str, str, str | None], pd.DataFrame],
    ) -> pd.DataFrame | None:
        symbol = candidate.benchmark_symbol or default_symbol
        if candidate.data_source == "csv":
            return None
        return benchmark_frames.get((symbol, candidate.resolution or "1d", candidate.feed))
