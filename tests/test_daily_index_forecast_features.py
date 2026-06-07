from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from app.daily_index_forecast.features import FEATURE_COLUMNS, build_feature_and_label_records
from app.daily_index_forecast.records import (
    DailyIndexFeatureRecord,
    DailyIndexLabelRecord,
    frame_to_records,
    records_to_frame,
)
from tests.daily_index_forecast_feature_test_utils import (
    assert_fields_equal,
    compound_return,
    make_cost_config,
    make_data_cache,
    make_feature_config,
    make_daily_index_universe,
    make_universe_frames,
    make_minimal_no_future_frames,
    mutate_future_bars,
    rolling_std,
    select_feature_record,
    select_label_record,
    session_summaries,
    zscore_last,
)


def _patch_universe_frames(monkeypatch, symbol_frame: pd.DataFrame, benchmark_frame: pd.DataFrame) -> None:
    def fake_load_universe_frames(*args, **kwargs):
        return {"SPY": symbol_frame}, benchmark_frame

    monkeypatch.setattr("app.daily_index_forecast.features.load_universe_frames", fake_load_universe_frames)


def test_daily_index_features_are_point_in_time_safe(monkeypatch) -> None:
    symbol_frames, benchmark_frame, session_days = make_universe_frames(session_count=25)
    symbol_frame = symbol_frames["SPY"]
    decision_time = "09:45"
    session_date = session_days[22]
    cutoff = pd.Timestamp(f"{session_date.isoformat()}T09:45:00", tz="America/New_York").tz_convert("UTC")

    universe = make_daily_index_universe(
        start_date=session_days[0],
        end_date=session_days[-1],
        decision_times=[decision_time],
    )
    feature_config = make_feature_config()
    costs = make_cost_config()
    cache = make_data_cache()

    _patch_universe_frames(monkeypatch, symbol_frame, benchmark_frame)
    original_features, original_labels, manifest = build_feature_and_label_records(
        universe,
        feature_config,
        costs,
        cache,
    )

    mutated_symbol = mutate_future_bars(symbol_frame, cutoff)
    mutated_benchmark = mutate_future_bars(benchmark_frame, cutoff, close_delta=75.0, high_delta=90.0, low_delta=55.0)

    _patch_universe_frames(monkeypatch, mutated_symbol, mutated_benchmark)
    mutated_features, mutated_labels, mutated_manifest = build_feature_and_label_records(
        universe,
        feature_config,
        costs,
        cache,
    )

    before = select_feature_record(original_features, symbol="SPY", session_date=session_date, decision_time=decision_time)
    after = select_feature_record(mutated_features, symbol="SPY", session_date=session_date, decision_time=decision_time)
    assert before.model_dump(mode="json") == after.model_dump(mode="json")

    assert before.bars_seen == 4
    assert before.minutes_since_open == 15
    assert before.minutes_to_close == 375
    assert before.opening_window_return_pct == pytest.approx(before.last_price / before.open_price - 1.0)
    assert before.opening_window_range_pct == pytest.approx((before.high_price - before.low_price) / before.open_price)

    assert_fields_equal(
        before,
        after,
        [
            "benchmark_return_5",
            "benchmark_return_20",
            "benchmark_volatility_20",
            "relative_return_20",
            "correlation_to_benchmark_20",
            "beta_to_benchmark_20",
        ],
    )

    assert mutated_manifest["joined_rows"] == manifest["joined_rows"]
    original_feature_columns = [col for col in FEATURE_COLUMNS if col in records_to_frame(original_features).columns]
    mutated_feature_columns = [col for col in FEATURE_COLUMNS if col in records_to_frame(mutated_features).columns]
    assert original_feature_columns == mutated_feature_columns == FEATURE_COLUMNS
    assert len(mutated_labels) == len(original_labels)


def test_daily_index_features_shift_rolling_and_prior_session_values(monkeypatch) -> None:
    symbol_frames, benchmark_frame, session_days = make_universe_frames(session_count=25)
    symbol_frame = symbol_frames["SPY"]
    universe = make_daily_index_universe(
        start_date=session_days[0],
        end_date=session_days[-1],
        decision_times=["09:45"],
    )
    feature_config = make_feature_config()
    costs = make_cost_config()
    cache = make_data_cache()

    _patch_universe_frames(monkeypatch, symbol_frame, benchmark_frame)
    features, _, _ = build_feature_and_label_records(universe, feature_config, costs, cache)
    feature = select_feature_record(features, symbol="SPY", session_date=session_days[22], decision_time="09:45")

    symbol_summary = session_summaries(symbol_frame)
    benchmark_summary = session_summaries(benchmark_frame)
    idx = symbol_summary.index[symbol_summary["session_date"] == session_days[22]][0]

    prior_session = symbol_summary.iloc[idx - 1]
    previous_5_returns = symbol_summary.iloc[idx - 5 : idx]["session_return_pct"].tolist()
    previous_20_returns = symbol_summary.iloc[idx - 20 : idx]["session_return_pct"].tolist()
    previous_20_volumes = symbol_summary.iloc[idx - 20 : idx]["volume"].tolist()
    benchmark_previous_20_returns = benchmark_summary.iloc[idx - 20 : idx]["session_return_pct"].tolist()

    assert feature.prior_session_return_pct == pytest.approx(float(prior_session["session_return_pct"]))
    assert feature.prior_session_range_pct == pytest.approx(float(prior_session["session_range_pct"]))
    assert feature.prior_session_volume == pytest.approx(float(prior_session["volume"]))

    assert feature.rolling_return_5 == pytest.approx(compound_return(previous_5_returns))
    assert feature.rolling_return_20 == pytest.approx(compound_return(previous_20_returns))
    assert feature.rolling_volatility_5 == pytest.approx(rolling_std(previous_5_returns))
    assert feature.rolling_volatility_20 == pytest.approx(rolling_std(previous_20_returns))
    assert feature.rolling_volume_z_20 == pytest.approx(zscore_last(previous_20_volumes))

    assert feature.benchmark_return_20 == pytest.approx(compound_return(benchmark_previous_20_returns))


def test_daily_index_labels_use_post_decision_tail_and_preserve_boundary(monkeypatch) -> None:
    symbol_frames, benchmark_frame, session_days = make_universe_frames(session_count=25)
    symbol_frame = symbol_frames["SPY"]
    decision_time = "09:45"
    session_date = session_days[22]
    cutoff = pd.Timestamp(f"{session_date.isoformat()}T09:45:00", tz="America/New_York").tz_convert("UTC")

    universe = make_daily_index_universe(
        start_date=session_days[0],
        end_date=session_days[-1],
        decision_times=[decision_time],
    )
    feature_config = make_feature_config()
    costs = make_cost_config()
    cache = make_data_cache()

    _patch_universe_frames(monkeypatch, symbol_frame, benchmark_frame)
    original_features, original_labels, _ = build_feature_and_label_records(
        universe,
        feature_config,
        costs,
        cache,
    )

    mutated_symbol = mutate_future_bars(symbol_frame, cutoff, close_delta=120.0, high_delta=150.0, low_delta=80.0)
    _patch_universe_frames(monkeypatch, mutated_symbol, benchmark_frame)
    mutated_features, mutated_labels, _ = build_feature_and_label_records(
        universe,
        feature_config,
        costs,
        cache,
    )

    feature = select_feature_record(original_features, symbol="SPY", session_date=session_date, decision_time=decision_time)
    label_before = select_label_record(original_labels, symbol="SPY", session_date=session_date, decision_time=decision_time)
    label_after = select_label_record(mutated_labels, symbol="SPY", session_date=session_date, decision_time=decision_time)
    mutated_feature = select_feature_record(mutated_features, symbol="SPY", session_date=session_date, decision_time=decision_time)

    assert label_before.entry_price == pytest.approx(feature.last_price)
    assert label_before.exit_timestamp > label_before.decision_timestamp
    assert label_before.exit_timestamp == label_after.exit_timestamp
    assert label_before.entry_price == label_after.entry_price
    assert label_before.exit_price != label_after.exit_price
    assert label_before.net_return_after_cost_bps != label_after.net_return_after_cost_bps
    assert label_before.positive_after_cost == (label_before.net_return_after_cost_bps > 0)

    assert feature.model_dump(mode="json") == mutated_feature.model_dump(mode="json")


def test_daily_index_feature_and_label_records_round_trip_parquet(tmp_path) -> None:
    feature_record = DailyIndexFeatureRecord(
        symbol="SPY",
        session_date=date(2024, 1, 5),
        decision_time="09:45",
        decision_timestamp=datetime(2024, 1, 5, 14, 45, tzinfo=UTC),
        session_open_timestamp=datetime(2024, 1, 5, 14, 30, tzinfo=UTC),
        session_close_timestamp=datetime(2024, 1, 5, 21, 0, tzinfo=UTC),
        bars_seen=4,
        opening_window_minutes=15,
        open_price=101.0,
        high_price=102.5,
        low_price=100.5,
        last_price=102.0,
        volume_so_far=4_000.0,
        dollar_volume_so_far=408_000.0,
        opening_window_return_pct=0.0099,
        opening_window_range_pct=0.0198,
        opening_window_close_location_pct=0.75,
        gap_return_pct=0.003,
        prior_session_return_pct=0.007,
        prior_session_range_pct=0.011,
        prior_session_volume=5_000.0,
        prior_session_realized_volatility=0.02,
        rolling_return_5=0.012,
        rolling_return_20=0.045,
        rolling_volatility_5=0.01,
        rolling_volatility_20=0.02,
        rolling_volume_z_20=1.3,
        benchmark_return_5=0.011,
        benchmark_return_20=0.04,
        benchmark_volatility_20=0.015,
        relative_return_20=0.005,
        correlation_to_benchmark_20=0.9,
        beta_to_benchmark_20=1.1,
        day_of_week=4,
        month=1,
        is_month_start=False,
        is_month_end=False,
        minutes_since_open=15,
        minutes_to_close=375,
    )
    label_record = DailyIndexLabelRecord(
        symbol="SPY",
        session_date=date(2024, 1, 5),
        decision_time="09:45",
        decision_timestamp=datetime(2024, 1, 5, 14, 45, tzinfo=UTC),
        exit_timestamp=datetime(2024, 1, 5, 21, 0, tzinfo=UTC),
        entry_price=102.0,
        exit_price=103.0,
        return_to_close_pct=0.0098,
        return_to_close_bps=98.0,
        net_return_after_cost_bps=92.5,
        positive_after_cost=True,
        intraday_max_runup_bps=120.0,
        intraday_max_drawdown_bps=-40.0,
        post_decision_realized_volatility_bps=35.0,
    )

    feature_path = tmp_path / "features.parquet"
    label_path = tmp_path / "labels.parquet"
    records_to_frame([feature_record]).to_parquet(feature_path, index=False)
    records_to_frame([label_record]).to_parquet(label_path, index=False)

    loaded_feature = frame_to_records(pd.read_parquet(feature_path), DailyIndexFeatureRecord)
    loaded_label = frame_to_records(pd.read_parquet(label_path), DailyIndexLabelRecord)

    assert loaded_feature == [feature_record]
    assert loaded_label == [label_record]
    assert isinstance(loaded_feature[0].is_month_start, bool)
    assert isinstance(loaded_label[0].positive_after_cost, bool)


def test_daily_index_feature_columns_match_canonical_schema(monkeypatch) -> None:
    symbol_frames, benchmark_frame, session_days = make_universe_frames(session_count=25)
    universe = make_daily_index_universe(
        start_date=session_days[0],
        end_date=session_days[-1],
        decision_times=["09:45"],
    )
    _patch_universe_frames(monkeypatch, symbol_frames["SPY"], benchmark_frame)

    features, labels, _ = build_feature_and_label_records(
        universe,
        make_feature_config(),
        make_cost_config(),
        make_data_cache(),
    )

    assert features
    assert labels
    feature_columns = [col for col in FEATURE_COLUMNS if col in records_to_frame(features).columns]
    assert feature_columns == FEATURE_COLUMNS


def test_daily_index_insufficient_history_and_no_future_bars_are_skipped(monkeypatch) -> None:
    symbol_frames, benchmark_frame = make_minimal_no_future_frames()
    universe = make_daily_index_universe(
        start_date=date(2024, 1, 2),
        end_date=date(2024, 1, 2),
        decision_times=["09:45"],
    )
    _patch_universe_frames(monkeypatch, symbol_frames["SPY"], benchmark_frame)

    features, labels, manifest = build_feature_and_label_records(
        universe,
        make_feature_config(),
        make_cost_config(),
        make_data_cache(),
    )

    assert features == []
    assert labels == []
    assert manifest["feature_rows"] == 0
    assert manifest["label_rows"] == 0
    assert manifest["dropped_feature_rows"] == 0
    assert manifest["dropped_label_rows"] == 1

    insufficient_symbol_frame = pd.DataFrame(
        [
            {"Open": 100.0, "High": 100.2, "Low": 99.9, "Close": 100.1, "Volume": 1_000.0},
        ],
        index=[pd.Timestamp("2024-01-02T09:50:00", tz="America/New_York").tz_convert("UTC")],
    )
    insufficient_benchmark_frame = insufficient_symbol_frame.copy()
    insufficient_benchmark_frame[["Open", "High", "Low", "Close"]] = insufficient_benchmark_frame[["Open", "High", "Low", "Close"]] + 100.0
    _patch_universe_frames(monkeypatch, insufficient_symbol_frame, insufficient_benchmark_frame)
    insufficient_features, insufficient_labels, insufficient_manifest = build_feature_and_label_records(
        universe,
        make_feature_config(),
        make_cost_config(),
        make_data_cache(),
    )

    assert insufficient_features == []
    assert insufficient_labels == []
    assert insufficient_manifest["feature_rows"] == 0
    assert insufficient_manifest["label_rows"] == 0
    assert insufficient_manifest["dropped_feature_rows"] == 1
    assert insufficient_manifest["dropped_label_rows"] == 1
