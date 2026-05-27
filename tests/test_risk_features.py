from __future__ import annotations

import pandas as pd

from app.risk.data.bars import bar_index_at_or_before
from app.risk.features.assemble import build_feature_snapshot
from app.risk.models import EnrichedCandidate, RiskDatasetConfig


def _candidate(timestamp: str) -> EnrichedCandidate:
    return EnrichedCandidate(
        candidate_id="feat-1",
        strategy_id="breakout_channel",
        symbol="TEST",
        timestamp=timestamp,
        entry_price=100.0,
        planned_stop_pct=0.02,
        planned_target_pct=0.04,
        planned_horizon_bars=5,
        metadata={"volume_ok": True},
        run_id="run-1",
        resolution="1d",
        data_source="csv",
        source_report_path="/tmp/report.json",
        csv_path="examples/data/sample_daily.csv",
    )


def _daily_frame() -> pd.DataFrame:
    rows = []
    for i in range(80):
        close = 100.0 + i * 0.5
        rows.append({"Open": close - 0.5, "High": close + 1.0, "Low": close - 1.0, "Close": close, "Volume": 10_000 + i * 100})
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    return pd.DataFrame(rows, index=index)


def test_features_are_point_in_time_safe():
    frame = _daily_frame()
    config = RiskDatasetConfig(min_history_bars=20)
    ts = "2024-02-15T00:00:00+00:00"
    before = build_feature_snapshot(_candidate(ts), frame=frame, config=config)

    mutated = frame.copy()
    decision_idx = bar_index_at_or_before(mutated, ts)
    assert decision_idx is not None
    future_idx = decision_idx + 5
    mutated.iloc[future_idx, mutated.columns.get_loc("Close")] = 999.0
    mutated.iloc[future_idx, mutated.columns.get_loc("High")] = 1000.0

    after = build_feature_snapshot(_candidate(ts), frame=mutated, config=config)
    assert before.return_20 == after.return_20
    assert before.rsi_14 == after.rsi_14
    assert before.feature_timestamp == after.feature_timestamp
    assert pd.Timestamp(before.feature_timestamp) <= pd.Timestamp(ts)


def test_features_insufficient_history():
    frame = _daily_frame().iloc[:10]
    config = RiskDatasetConfig(min_history_bars=60)
    snapshot = build_feature_snapshot(
        _candidate("2024-01-08T00:00:00+00:00"),
        frame=frame,
        config=config,
    )
    assert snapshot.feature_quality_flag == "INSUFFICIENT_HISTORY"
    assert snapshot.return_20 is None


def test_metadata_features_flattened():
    frame = _daily_frame()
    config = RiskDatasetConfig(min_history_bars=20)
    snapshot = build_feature_snapshot(
        _candidate("2024-02-15T00:00:00+00:00"),
        frame=frame,
        config=config,
    )
    assert snapshot.metadata_features["meta_volume_ok"] is True
