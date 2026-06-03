from __future__ import annotations

import json
import logging
import os
import random
import socket
import time
from datetime import UTC
from datetime import date
from datetime import timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request
from urllib.request import urlopen

import pandas as pd

from app.config.models import AlpacaDataSource, CsvDataSource, DataCacheConfig, YahooDataSource
from app.data.cache import CacheKey, ParquetDataCache

logger = logging.getLogger(__name__)


def _is_temporary_dns_failure(exc: URLError) -> bool:
    """
    Best-effort detection for transient DNS failures inside containers/K8s.
    Common forms:
      - socket.gaierror: [Errno -3] Temporary failure in name resolution
      - OSError-like objects with errno -3
    """
    reason = getattr(exc, "reason", None)
    if isinstance(reason, socket.gaierror):
        return reason.errno == -3
    errno = getattr(reason, "errno", None)
    return errno == -3


def _sleep_backoff(attempt_index: int, *, base_s: float = 1.0, cap_s: float = 30.0) -> float:
    # Exponential backoff with jitter. attempt_index is 0-based.
    delay = min(cap_s, base_s * (2**attempt_index))
    jitter = random.uniform(0.0, min(1.0, delay * 0.2))
    time.sleep(delay + jitter)
    return delay + jitter


def _normalize_ohlcv_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()

    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)

    lower = {str(c).lower(): c for c in out.columns}
    required = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    missing = [k for k in required if k not in lower]
    if missing:
        raise RuntimeError(f"Data is missing required columns: {sorted(missing)}")

    selected = out[[lower[k] for k in required]]
    selected.columns = [required[k] for k in required]

    if not isinstance(selected.index, pd.DatetimeIndex):
        selected.index = pd.to_datetime(selected.index, errors="coerce")
    selected = selected[~selected.index.isna()]
    selected = selected.sort_index()
    return selected


def build_csv_data_feed(config: CsvDataSource, start_date: date, end_date: date) -> pd.DataFrame:
    df = pd.read_csv(config.path)
    if config.datetime_column not in df.columns:
        raise RuntimeError(f"CSV missing datetime column '{config.datetime_column}'")

    dt = pd.to_datetime(df[config.datetime_column], format=config.date_format, errors="coerce")
    if dt.isna().any():
        dt = pd.to_datetime(df[config.datetime_column], errors="coerce")
    if dt.isna().any():
        raise RuntimeError(f"CSV has invalid datetime values in '{config.datetime_column}'")

    col_map = {
        config.open_column: "Open",
        config.high_column: "High",
        config.low_column: "Low",
        config.close_column: "Close",
        config.volume_column: "Volume",
    }
    missing = [src for src in col_map if src not in df.columns]
    if missing:
        raise RuntimeError(f"CSV missing required price columns: {sorted(missing)}")

    out = df[list(col_map.keys())].rename(columns=col_map)
    out.index = dt

    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
    out = out.loc[(out.index >= start_ts) & (out.index <= end_ts)]
    if out.empty:
        raise RuntimeError("No CSV data found in requested date range")
    return _normalize_ohlcv_frame(out)


def build_yahoo_data_feed(config: YahooDataSource, start_date: date, end_date: date) -> pd.DataFrame:
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
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
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
            return _normalize_ohlcv_frame(cached.frame), cached.status

    df = _download_yahoo(yf, config, start_date, end_date)

    if cache_config and cache_config.enabled:
        cache = ParquetDataCache(Path(cache_config.directory))
        cache.put(key, df)
    if force_refresh:
        cache_status = "force_refresh"
    return df, cache_status


def build_alpaca_data_feed(config: AlpacaDataSource, start_date: date, end_date: date) -> pd.DataFrame:
    feed, _ = build_alpaca_data_feed_with_cache(
        config,
        start_date,
        end_date,
        cache_config=None,
    )
    return feed


def build_alpaca_data_feed_with_cache(
    config: AlpacaDataSource,
    start_date: date,
    end_date: date,
    cache_config: DataCacheConfig | None,
    force_refresh: bool = False,
) -> tuple[pd.DataFrame, str]:
    key = CacheKey(
        source="alpaca",
        symbol=config.symbol,
        interval=config.interval,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        feed=config.feed,
    )
    cache_status = "miss"
    if cache_config and cache_config.enabled and not force_refresh:
        ttl_seconds = cache_config.ttl_by_interval.get(config.interval, 24 * 60 * 60)
        cache = ParquetDataCache(Path(cache_config.directory))
        cached = cache.get(key, timedelta(seconds=ttl_seconds))
        cache_status = cached.status
        if cached.frame is not None:
            return _normalize_ohlcv_frame(cached.frame), cached.status

    df = _download_alpaca(config, start_date, end_date)

    if cache_config and cache_config.enabled:
        cache = ParquetDataCache(Path(cache_config.directory))
        cache.put(key, df)
    if force_refresh:
        cache_status = "force_refresh"
    return df, cache_status


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
    return _normalize_ohlcv_frame(df)


def _download_alpaca(config: AlpacaDataSource, start_date: date, end_date: date) -> pd.DataFrame:
    key = os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise RuntimeError("Alpaca credentials missing: set ALPACA_API_KEY and ALPACA_SECRET_KEY")

    timeframe = _alpaca_timeframe(config.interval)
    start_ts = pd.Timestamp(start_date).tz_localize(UTC).isoformat().replace("+00:00", "Z")
    # Alpaca treats end as exclusive; advance one day so stop_date includes the full session.
    end_ts = (
        (pd.Timestamp(end_date) + pd.Timedelta(days=1))
        .tz_localize(UTC)
        .isoformat()
        .replace("+00:00", "Z")
    )

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
        last_exc: URLError | None = None
        for attempt in range(6):
            try:
                with urlopen(req, timeout=30) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                last_exc = None
                break
            except HTTPError as exc:
                body = exc.read().decode("utf-8", errors="ignore")
                raise RuntimeError(f"Alpaca request failed ({exc.code}): {body or exc.reason}") from exc
            except URLError as exc:
                last_exc = exc
                if not _is_temporary_dns_failure(exc) or attempt == 5:
                    raise RuntimeError(f"Failed to reach Alpaca data API: {exc.reason}") from exc
                delay_s = _sleep_backoff(attempt)
                logger.warning(
                    "Alpaca DNS lookup failed (temporary). Retrying in %.2fs (attempt %d/%d). Error=%r",
                    delay_s,
                    attempt + 1,
                    6,
                    exc.reason,
                )
        if last_exc is not None:
            # Defensive: should only happen if the loop exits unexpectedly.
            raise RuntimeError(f"Failed to reach Alpaca data API: {last_exc.reason}") from last_exc

        bars.extend(payload.get("bars") or [])
        page_token = payload.get("next_page_token")
        if not page_token:
            break

    if not bars:
        raise RuntimeError(f"No Alpaca data found for symbol {config.symbol}")

    df = pd.DataFrame(bars)
    rename_map = {"o": "Open", "h": "High", "l": "Low", "c": "Close", "v": "Volume", "t": "datetime"}
    df = df.rename(columns=rename_map)
    if "datetime" not in df.columns:
        raise RuntimeError(f"Alpaca data is missing time field for {config.symbol}")
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    df = df.set_index("datetime").sort_index()
    return _normalize_ohlcv_frame(df)


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
