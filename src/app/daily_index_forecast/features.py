from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from statistics import NormalDist
from typing import Any

import numpy as np
import pandas as pd

from app.backtests.argo_progress import ARGO_PROGRESS_TOTAL, ThrottledProgressWriter, resolve_progress_file
from app.config.models import AlpacaDataSource, CsvDataSource, DataCacheConfig, YahooDataSource
from app.data.loaders import build_alpaca_data_feed_with_cache, build_csv_data_feed, build_yahoo_data_feed_with_cache
from app.daily_index_forecast.models import (
    DailyIndexCostConfig,
    DailyIndexFeatureConfig,
    DailyIndexSeriesSpec,
    DailyIndexUniverseConfig,
)
from app.daily_index_forecast.records import (
    DailyIndexFeatureRecord,
    DailyIndexLabelRecord,
    records_to_frame,
)

NY_TZ = "America/New_York"
SESSION_OPEN_TIME = time(9, 30)
SESSION_CLOSE_TIME = time(16, 0)
DEFAULT_FEATURE_VERSION = "daily_index_features_v1"
DEFAULT_LABEL_VERSION = "daily_index_labels_v1"
DEFAULT_DATASET_VERSION = "daily_index_dataset_v1"
DEFAULT_MODEL_VERSION = "daily_index_model_v1"

FEATURE_COLUMNS: list[str] = [
    "bars_seen",
    "opening_window_minutes",
    "open_price",
    "high_price",
    "low_price",
    "last_price",
    "volume_so_far",
    "dollar_volume_so_far",
    "opening_window_return_pct",
    "opening_window_range_pct",
    "opening_window_close_location_pct",
    "gap_return_pct",
    "prior_session_return_pct",
    "prior_session_range_pct",
    "prior_session_volume",
    "prior_session_realized_volatility",
    "rolling_return_5",
    "rolling_return_20",
    "rolling_volatility_5",
    "rolling_volatility_20",
    "rolling_volume_z_20",
    "benchmark_return_5",
    "benchmark_return_20",
    "benchmark_volatility_20",
    "relative_return_20",
    "correlation_to_benchmark_20",
    "beta_to_benchmark_20",
    "day_of_week",
    "month",
    "is_month_start",
    "is_month_end",
    "minutes_since_open",
    "minutes_to_close",
]


@dataclass(frozen=True)
class SessionSummaries:
    symbol: str
    frame: pd.DataFrame
    session_summaries: pd.DataFrame


def _json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def config_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=_json_default).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _ensure_utc_index(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out.index = pd.to_datetime(out.index, utc=True, errors="coerce")
    out = out[~out.index.isna()].sort_index()
    return out


def _load_source(
    source: CsvDataSource | YahooDataSource | AlpacaDataSource,
    start_date: date,
    end_date: date,
    cache_config: DataCacheConfig,
    *,
    force_refresh: bool = False,
) -> pd.DataFrame:
    if isinstance(source, CsvDataSource):
        return build_csv_data_feed(source, start_date, end_date)
    if isinstance(source, YahooDataSource):
        frame, _ = build_yahoo_data_feed_with_cache(
            source,
            start_date,
            end_date,
            cache_config=cache_config,
            force_refresh=force_refresh,
        )
        return frame
    if isinstance(source, AlpacaDataSource):
        frame, _ = build_alpaca_data_feed_with_cache(
            source,
            start_date,
            end_date,
            cache_config=cache_config,
            force_refresh=force_refresh,
        )
        return frame
    raise TypeError(f"Unsupported data source type: {type(source)!r}")


def load_universe_frames(
    universe: DailyIndexUniverseConfig,
    cache_config: DataCacheConfig,
    *,
    force_refresh: bool = False,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame | None]:
    start_date = universe.start_date
    end_date = universe.end_date

    frames: dict[str, pd.DataFrame] = {}
    for spec in universe.symbols:
        symbol = spec.symbol or getattr(spec.data, "symbol", None)
        if not symbol:
            raise ValueError("Each symbol spec requires a symbol")
        frame = _load_source(spec.data, start_date, end_date, cache_config, force_refresh=force_refresh)
        frames[symbol] = _ensure_utc_index(frame)

    benchmark_frame: pd.DataFrame | None = None
    if universe.benchmark is not None:
        benchmark_frame = _load_source(
            universe.benchmark.data,
            start_date,
            end_date,
            cache_config,
            force_refresh=force_refresh,
        )
        benchmark_frame = _ensure_utc_index(benchmark_frame)
    return frames, benchmark_frame


def _to_local(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        return ts.tz_localize("UTC").tz_convert(NY_TZ)
    return ts.tz_convert(NY_TZ)


def _session_date(ts: pd.Timestamp) -> date:
    return _to_local(ts).date()


def _session_bounds(session_day: date) -> tuple[pd.Timestamp, pd.Timestamp]:
    open_local = pd.Timestamp.combine(session_day, SESSION_OPEN_TIME).tz_localize(NY_TZ)
    close_local = pd.Timestamp.combine(session_day, SESSION_CLOSE_TIME).tz_localize(NY_TZ)
    return open_local.tz_convert("UTC"), close_local.tz_convert("UTC")


def _session_frame(frame: pd.DataFrame, session_day: date) -> pd.DataFrame:
    session_mask = frame.index.map(_session_date) == session_day
    return frame.loc[session_mask].sort_index()


def _build_session_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for session_day in sorted({_session_date(ts) for ts in frame.index}):
        session = _session_frame(frame, session_day)
        if session.empty:
            continue

        open_price = float(session["Open"].iloc[0])
        close_price = float(session["Close"].iloc[-1])
        high_price = float(session["High"].max())
        low_price = float(session["Low"].min())
        volume = float(session["Volume"].sum())
        close_prev = float(session["Close"].iloc[-2]) if len(session) > 1 else close_price
        log_returns = np.diff(np.log(session["Close"].astype(float).replace(0, np.nan).dropna().values))
        realized_volatility = float(np.nanstd(log_returns)) if log_returns.size else 0.0
        rows.append(
            {
                "session_date": session_day,
                "open_price": open_price,
                "high_price": high_price,
                "low_price": low_price,
                "close_price": close_price,
                "volume": volume,
                "dollar_volume": float((session["Close"].astype(float) * session["Volume"].astype(float)).sum()),
                "session_return_pct": (close_price / open_price - 1.0) if open_price else None,
                "session_close_return_pct": (close_price / close_prev - 1.0) if close_prev else None,
                "session_range_pct": ((high_price - low_price) / open_price) if open_price else None,
                "session_realized_volatility": realized_volatility,
            }
        )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("session_date").reset_index(drop=True)


def _rolling_window_value(values: pd.Series, window: int, fn: str) -> float | None:
    if len(values) < window:
        return None
    series = values.tail(window).astype(float)
    if fn == "return":
        return float(np.prod(1.0 + series.to_numpy()) - 1.0)
    if fn == "volatility":
        return float(series.std(ddof=0))
    if fn == "mean":
        return float(series.mean())
    if fn == "zscore":
        std = float(series.std(ddof=0))
        if std == 0:
            return None
        return float((series.iloc[-1] - series.mean()) / std)
    raise ValueError(f"Unknown rolling function '{fn}'")


def _correlation_beta(symbol_returns: pd.Series, benchmark_returns: pd.Series) -> tuple[float | None, float | None]:
    if len(symbol_returns) < 3 or len(benchmark_returns) < 3:
        return None, None
    aligned = pd.concat([symbol_returns, benchmark_returns], axis=1).dropna()
    if len(aligned) < 3:
        return None, None
    x = aligned.iloc[:, 1].astype(float)
    y = aligned.iloc[:, 0].astype(float)
    corr = float(y.corr(x)) if len(aligned) > 1 else None
    var_x = float(x.var(ddof=0))
    beta = float(y.cov(x) / var_x) if var_x else None
    return corr, beta


def _decision_timestamp(session_day: date, decision_time: str) -> pd.Timestamp:
    parts = decision_time.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = int(parts[2]) if len(parts) > 2 else 0
    local = pd.Timestamp.combine(session_day, time(hours, minutes, seconds)).tz_localize(NY_TZ)
    return local.tz_convert("UTC")


def _future_tail(session: pd.DataFrame, decision_ts: pd.Timestamp) -> pd.DataFrame:
    return session.loc[session.index > decision_ts].sort_index()


def build_feature_and_label_records(
    universe: DailyIndexUniverseConfig,
    feature_config: DailyIndexFeatureConfig,
    costs: DailyIndexCostConfig,
    cache_config: DataCacheConfig,
    *,
    force_refresh: bool = False,
) -> tuple[list[DailyIndexFeatureRecord], list[DailyIndexLabelRecord], dict[str, Any]]:
    frames, benchmark_frame = load_universe_frames(universe, cache_config, force_refresh=force_refresh)
    benchmark_summary = _build_session_summary(benchmark_frame) if benchmark_frame is not None else pd.DataFrame()
    progress_path = resolve_progress_file()
    progress_writer = ThrottledProgressWriter(progress_path) if progress_path is not None else None
    if progress_writer is not None:
        progress_writer.write_immediate(0)

    feature_records: list[DailyIndexFeatureRecord] = []
    label_records: list[DailyIndexLabelRecord] = []
    total_source_rows = 0
    skipped_feature_rows = 0
    skipped_label_rows = 0
    total_steps = 0

    for spec in universe.symbols:
        symbol = spec.symbol or getattr(spec.data, "symbol", None)
        if not symbol:
            raise ValueError("Each symbol spec requires a symbol")
        session_summary = _build_session_summary(frames[symbol])
        if not session_summary.empty:
            total_steps += len(session_summary.index) * len(universe.decision_times)

    completed_steps = 0

    for spec in universe.symbols:
        symbol = spec.symbol or getattr(spec.data, "symbol", None)
        if not symbol:
            raise ValueError("Each symbol spec requires a symbol")
        frame = frames[symbol]
        total_source_rows += len(frame)
        session_summary = _build_session_summary(frame)
        if session_summary.empty:
            continue

        summary_index = session_summary.set_index("session_date")
        symbol_returns = summary_index["session_return_pct"].astype(float)
        benchmark_returns = benchmark_summary.set_index("session_date")["session_return_pct"].astype(float) if not benchmark_summary.empty else pd.Series(dtype=float)

        for session_day in summary_index.index.to_list():
            session = _session_frame(frame, session_day)
            if session.empty:
                skipped_feature_rows += 1
                continue

            day_summary = summary_index.loc[session_day]
            prev_day = None
            prev_summary = None
            prev_idx = summary_index.index.get_indexer([session_day])[0] - 1
            if prev_idx >= 0:
                prev_day = summary_index.index[prev_idx]
                prev_summary = summary_index.iloc[prev_idx]

            for decision_time in universe.decision_times:
                decision_ts = _decision_timestamp(session_day, decision_time)
                completed_steps += 1
                if progress_writer is not None and total_steps > 0:
                    progress_writer.write(round(min(1.0, completed_steps / total_steps) * ARGO_PROGRESS_TOTAL))
                hist = session.loc[session.index <= decision_ts]
                if hist.empty:
                    skipped_feature_rows += 1
                    skipped_label_rows += 1
                    continue
                future = _future_tail(session, decision_ts)
                if future.empty:
                    skipped_label_rows += 1
                    continue

                open_price = float(hist["Open"].iloc[0])
                high_price = float(hist["High"].max())
                low_price = float(hist["Low"].min())
                last_price = float(hist["Close"].iloc[-1])
                volume_so_far = float(hist["Volume"].sum())
                dollar_volume_so_far = float((hist["Close"].astype(float) * hist["Volume"].astype(float)).sum())
                opening_window_return_pct = (last_price / open_price - 1.0) if open_price else None
                opening_window_range_pct = ((high_price - low_price) / open_price) if open_price else None
                opening_window_close_location_pct = (
                    (last_price - low_price) / (high_price - low_price) if high_price > low_price else 0.5
                )
                prev_close = float(prev_summary["close_price"]) if prev_summary is not None else None
                gap_return_pct = (open_price / prev_close - 1.0) if prev_close else None

                window_returns = symbol_returns.loc[:session_day].dropna()
                benchmark_window_returns = (
                    benchmark_returns.loc[:session_day].dropna()
                    if not benchmark_summary.empty
                    else pd.Series(dtype=float)
                )

                rolling_return_5 = _rolling_window_value(window_returns.iloc[:-1] if len(window_returns) > 1 else window_returns, 5, "return")
                rolling_return_20 = _rolling_window_value(window_returns.iloc[:-1] if len(window_returns) > 1 else window_returns, 20, "return")
                rolling_volatility_5 = _rolling_window_value(window_returns.iloc[:-1] if len(window_returns) > 1 else window_returns, 5, "volatility")
                rolling_volatility_20 = _rolling_window_value(window_returns.iloc[:-1] if len(window_returns) > 1 else window_returns, 20, "volatility")
                rolling_volume_z_20 = _rolling_window_value(
                    summary_index["volume"].iloc[: summary_index.index.get_indexer([session_day])[0]],
                    20,
                    "zscore",
                )

                benchmark_return_5 = benchmark_return_20 = benchmark_volatility_20 = relative_return_20 = None
                correlation_to_benchmark_20 = beta_to_benchmark_20 = None
                if not benchmark_summary.empty:
                    symbol_history_returns = window_returns.iloc[:-1] if len(window_returns) > 1 else window_returns
                    benchmark_history_returns = (
                        benchmark_window_returns.iloc[:-1] if len(benchmark_window_returns) > 1 else benchmark_window_returns
                    )
                    benchmark_return_5 = _rolling_window_value(benchmark_window_returns.iloc[:-1] if len(benchmark_window_returns) > 1 else benchmark_window_returns, 5, "return")
                    benchmark_return_20 = _rolling_window_value(benchmark_window_returns.iloc[:-1] if len(benchmark_window_returns) > 1 else benchmark_window_returns, 20, "return")
                    benchmark_volatility_20 = _rolling_window_value(
                        benchmark_window_returns.iloc[:-1] if len(benchmark_window_returns) > 1 else benchmark_window_returns,
                        20,
                        "volatility",
                    )
                    if rolling_return_20 is not None and benchmark_return_20 is not None:
                        relative_return_20 = rolling_return_20 - benchmark_return_20
                    corr, beta = _correlation_beta(
                        symbol_history_returns.iloc[-20:],
                        benchmark_history_returns.iloc[-20:],
                    )
                    correlation_to_benchmark_20 = corr
                    beta_to_benchmark_20 = beta

                minutes_since_open = int((hist.index[-1].tz_convert(NY_TZ) - hist.index[0].tz_convert(NY_TZ)).total_seconds() // 60)
                _, session_close_utc = _session_bounds(session_day)
                minutes_to_close = int((session_close_utc - hist.index[-1]).total_seconds() // 60)

                feature_records.append(
                    DailyIndexFeatureRecord(
                        symbol=symbol,
                        session_date=session_day,
                        decision_time=decision_time,
                        decision_timestamp=decision_ts.to_pydatetime(),
                        session_open_timestamp=_session_bounds(session_day)[0].to_pydatetime(),
                        session_close_timestamp=_session_bounds(session_day)[1].to_pydatetime(),
                        bars_seen=int(len(hist)),
                        opening_window_minutes=int(feature_config.opening_window_minutes),
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        last_price=last_price,
                        volume_so_far=volume_so_far,
                        dollar_volume_so_far=dollar_volume_so_far,
                        opening_window_return_pct=opening_window_return_pct,
                        opening_window_range_pct=opening_window_range_pct,
                        opening_window_close_location_pct=opening_window_close_location_pct,
                        gap_return_pct=gap_return_pct,
                        prior_session_return_pct=float(prev_summary["session_return_pct"]) if prev_summary is not None and prev_summary["session_return_pct"] is not None else None,
                        prior_session_range_pct=float(prev_summary["session_range_pct"]) if prev_summary is not None and prev_summary["session_range_pct"] is not None else None,
                        prior_session_volume=float(prev_summary["volume"]) if prev_summary is not None else None,
                        prior_session_realized_volatility=float(prev_summary["session_realized_volatility"]) if prev_summary is not None else None,
                        rolling_return_5=rolling_return_5,
                        rolling_return_20=rolling_return_20,
                        rolling_volatility_5=rolling_volatility_5,
                        rolling_volatility_20=rolling_volatility_20,
                        rolling_volume_z_20=rolling_volume_z_20,
                        benchmark_return_5=benchmark_return_5,
                        benchmark_return_20=benchmark_return_20,
                        benchmark_volatility_20=benchmark_volatility_20,
                        relative_return_20=relative_return_20,
                        correlation_to_benchmark_20=correlation_to_benchmark_20,
                        beta_to_benchmark_20=beta_to_benchmark_20,
                        day_of_week=int(pd.Timestamp(session_day).dayofweek),
                        month=int(pd.Timestamp(session_day).month),
                        is_month_start=bool(pd.Timestamp(session_day).is_month_start),
                        is_month_end=bool(pd.Timestamp(session_day).is_month_end),
                        minutes_since_open=minutes_since_open,
                        minutes_to_close=minutes_to_close,
                        feature_quality_flag="OK",
                    )
                )

                exit_price = float(future["Close"].iloc[-1])
                return_to_close_pct = exit_price / last_price - 1.0 if last_price else 0.0
                return_to_close_bps = return_to_close_pct * 10000.0
                net_return_after_cost_bps = return_to_close_bps - costs.roundtrip_bps
                intraday_high = float(future["High"].max())
                intraday_low = float(future["Low"].min())
                intraday_max_runup_bps = ((intraday_high / last_price - 1.0) * 10000.0) if last_price else None
                intraday_max_drawdown_bps = ((intraday_low / last_price - 1.0) * 10000.0) if last_price else None
                future_returns = future["Close"].astype(float).pct_change().dropna()
                post_decision_realized_volatility_bps = (
                    float(future_returns.std(ddof=0) * 10000.0) if not future_returns.empty else None
                )

                label_records.append(
                    DailyIndexLabelRecord(
                        symbol=symbol,
                        session_date=session_day,
                        decision_time=decision_time,
                        decision_timestamp=decision_ts.to_pydatetime(),
                        exit_timestamp=future.index[-1].to_pydatetime(),
                        entry_price=last_price,
                        exit_price=exit_price,
                        return_to_close_pct=return_to_close_pct,
                        return_to_close_bps=return_to_close_bps,
                        net_return_after_cost_bps=net_return_after_cost_bps,
                        positive_after_cost=bool(net_return_after_cost_bps > 0),
                        intraday_max_runup_bps=intraday_max_runup_bps,
                        intraday_max_drawdown_bps=intraday_max_drawdown_bps,
                        post_decision_realized_volatility_bps=post_decision_realized_volatility_bps,
                        label_quality_flag="OK",
                    )
                )

    feature_df = records_to_frame(feature_records)
    label_df = records_to_frame(label_records)
    joined_rows = 0
    if not feature_df.empty and not label_df.empty:
        joined_rows = len(
            pd.merge(
                feature_df,
                label_df,
                on=["symbol", "session_date", "decision_time", "decision_timestamp"],
                how="inner",
            )
        )

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "total_source_rows": int(total_source_rows),
        "feature_rows": int(len(feature_records)),
        "label_rows": int(len(label_records)),
        "joined_rows": int(joined_rows),
        "dropped_feature_rows": int(skipped_feature_rows),
        "dropped_label_rows": int(skipped_label_rows),
    }
    if progress_writer is not None:
        progress_writer.write_immediate(ARGO_PROGRESS_TOTAL)
    return feature_records, label_records, manifest


def normal_probability_above_threshold(predicted_return_bps: float, threshold_bps: float, residual_std: float) -> float:
    if residual_std <= 0:
        return 1.0 if predicted_return_bps >= threshold_bps else 0.0
    z = (threshold_bps - predicted_return_bps) / residual_std
    return float(1.0 - NormalDist().cdf(z))
