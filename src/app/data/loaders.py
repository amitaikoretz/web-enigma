from __future__ import annotations

import json
import os
from datetime import UTC
from datetime import date
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

import backtrader as bt
import pandas as pd

from app.config.models import AlpacaDataSource, CsvDataSource, DataCacheConfig, YahooDataSource
from app.data.cache import CacheKey, ParquetDataCache


def build_csv_data_feed(config: CsvDataSource, start_date: date, end_date: date) -> bt.feeds.GenericCSVData:
    return bt.feeds.GenericCSVData(
        dataname=config.path,
        dtformat=config.date_format,
        datetime=0,
        open=1,
        high=2,
        low=3,
        close=4,
        volume=5,
        openinterest=6,
        fromdate=start_date,
        todate=end_date,
    )


def build_yahoo_data_feed(config: YahooDataSource, start_date: date, end_date: date) -> bt.feeds.PandasData:
    feed, _ = build_yahoo_data_feed_with_cache(
        config,
        start_date,
        end_date,
        cache_config=None,
        force_refresh=False,
    )
    return feed


def build_yahoo_data_feed_with_cache(
    config: YahooDataSource,
    start_date: date,
    end_date: date,
    cache_config: DataCacheConfig | None,
    force_refresh: bool,
) -> tuple[bt.feeds.PandasData, str]:
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is required for yahoo data source") from exc

    key = CacheKey(
        source="yahoo",
        symbol=config.symbol,
        interval=config.interval,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    cache_status = "miss"
    if cache_config and cache_config.enabled and not force_refresh:
        ttl_seconds = cache_config.ttl_by_interval.get(config.interval, 24 * 60 * 60)
        cache = ParquetDataCache(Path(cache_config.directory))
        cached = cache.get(key, timedelta(seconds=ttl_seconds))
        cache_status = cached.status
        if cached.frame is not None:
            return bt.feeds.PandasData(dataname=cached.frame), cached.status

    df = _download_yahoo(yf, config, start_date, end_date)

    if cache_config and cache_config.enabled:
        cache = ParquetDataCache(Path(cache_config.directory))
        cache.put(key, df)
    if force_refresh:
        cache_status = "force_refresh"
    return bt.feeds.PandasData(dataname=df), cache_status


def build_alpaca_data_feed_with_cache(
    config: AlpacaDataSource,
    start_date: date,
    end_date: date,
    cache_config: DataCacheConfig | None,
    force_refresh: bool,
) -> tuple[bt.feeds.PandasData, str]:
    key = CacheKey(
        source="alpaca",
        symbol=config.symbol,
        interval=config.interval,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    cache_status = "miss"
    if cache_config and cache_config.enabled and not force_refresh:
        ttl_seconds = cache_config.ttl_by_interval.get(config.interval, 24 * 60 * 60)
        cache = ParquetDataCache(Path(cache_config.directory))
        cached = cache.get(key, timedelta(seconds=ttl_seconds))
        cache_status = cached.status
        if cached.frame is not None:
            return bt.feeds.PandasData(dataname=cached.frame), cached.status

    df = _download_alpaca(config, start_date, end_date)

    if cache_config and cache_config.enabled:
        cache = ParquetDataCache(Path(cache_config.directory))
        cache.put(key, df)
    if force_refresh:
        cache_status = "force_refresh"
    return bt.feeds.PandasData(dataname=df), cache_status


def _download_yahoo(yf, config: YahooDataSource, start_date: date, end_date: date) -> pd.DataFrame:
    df = yf.download(
        config.symbol,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        interval=config.interval,
        progress=False,
        auto_adjust=False,
    )
    if df.empty:
        raise RuntimeError(f"No Yahoo data found for symbol {config.symbol}")

    # yfinance may return MultiIndex/tuple columns; Backtrader expects flat string columns.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [str(c).lower() for c in df.columns]

    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        raise RuntimeError(
            f"Yahoo data is missing required columns for {config.symbol}: {sorted(missing)}"
        )
    return df


def _download_alpaca(config: AlpacaDataSource, start_date: date, end_date: date) -> pd.DataFrame:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Alpaca credentials missing: set ALPACA_API_KEY and ALPACA_SECRET_KEY")

    timeframe = _alpaca_timeframe(config.interval)
    start_ts = pd.Timestamp(start_date).tz_localize(UTC).isoformat().replace("+00:00", "Z")
    end_ts = pd.Timestamp(end_date).tz_localize(UTC).isoformat().replace("+00:00", "Z")

    base_url = f"https://data.alpaca.markets/v2/stocks/{config.symbol}/bars"
    page_token: str | None = None
    bars: list[dict] = []

    while True:
        params = {
            "timeframe": timeframe,
            "start": start_ts,
            "end": end_ts,
            "limit": "10000",
            "adjustment": "raw",
            "feed": config.feed,
            "sort": "asc",
        }
        if page_token:
            params["page_token"] = page_token

        req = Request(
            f"{base_url}?{urlencode(params)}",
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "accept": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Alpaca request failed ({exc.code}): {body or exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(f"Failed to reach Alpaca data API: {exc.reason}") from exc

        bars.extend(payload.get("bars", []))
        page_token = payload.get("next_page_token")
        if not page_token:
            break

    if not bars:
        raise RuntimeError(f"No Alpaca data found for symbol {config.symbol}")

    df = pd.DataFrame(bars)
    rename_map = {"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "t": "datetime"}
    df = df.rename(columns=rename_map)
    if "datetime" not in df.columns:
        raise RuntimeError(f"Alpaca data is missing time field for {config.symbol}")
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime").sort_index()

    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        raise RuntimeError(
            f"Alpaca data is missing required columns for {config.symbol}: {sorted(missing)}"
        )
    return df


def _alpaca_timeframe(interval: str) -> str:
    mapping = {
        "1m": "1Min",
        "5m": "5Min",
        "15m": "15Min",
        "1h": "1Hour",
        "1d": "1Day",
    }
    if interval not in mapping:
        raise RuntimeError(
            f"Unsupported Alpaca interval '{interval}'. Supported: {', '.join(sorted(mapping))}"
        )
    return mapping[interval]
