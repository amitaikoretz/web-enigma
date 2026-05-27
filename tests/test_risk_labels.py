from __future__ import annotations

import pandas as pd
import pytest

from app.risk.labels.path_labels import label_long_candidate


def _frame(rows: list[dict[str, float]]) -> pd.DataFrame:
    index = pd.date_range("2024-01-01", periods=len(rows), freq="D", tz="UTC")
    return pd.DataFrame(rows, index=index)


def test_label_stop_hit_before_target():
    frame = _frame(
        [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100},
            {"Open": 100, "High": 101, "Low": 97, "Close": 98},
            {"Open": 98, "High": 99, "Low": 96, "Close": 97},
            {"Open": 97, "High": 98, "Low": 95, "Close": 96},
        ]
    )
    label = label_long_candidate(
        candidate_id="c1",
        label_version="labels_v1",
        entry_price=100.0,
        entry_type="CLOSE",
        fill_model="close",
        planned_stop_pct=0.03,
        planned_target_pct=0.05,
        planned_horizon_bars=3,
        decision_idx=0,
        frame=frame,
    )
    assert label.hit_stop is True
    assert label.exit_reason == "STOP"
    assert label.hit_stop_before_target is True
    assert label.mae_abs_pct == pytest.approx(0.03)
    assert label.label_quality_flag == "OK"


def test_label_target_hit():
    frame = _frame(
        [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100},
            {"Open": 100, "High": 106, "Low": 99.5, "Close": 105},
            {"Open": 105, "High": 106, "Low": 104, "Close": 105},
        ]
    )
    label = label_long_candidate(
        candidate_id="c2",
        label_version="labels_v1",
        entry_price=100.0,
        entry_type="CLOSE",
        fill_model="close",
        planned_stop_pct=0.05,
        planned_target_pct=0.04,
        planned_horizon_bars=2,
        decision_idx=0,
        frame=frame,
    )
    assert label.hit_target is True
    assert label.exit_reason == "TARGET"
    assert label.hit_stop_before_target is False


def test_label_time_exit():
    frame = _frame(
        [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100},
            {"Open": 100, "High": 101, "Low": 99.5, "Close": 100.5},
            {"Open": 100.5, "High": 101, "Low": 99.8, "Close": 100.2},
        ]
    )
    label = label_long_candidate(
        candidate_id="c3",
        label_version="labels_v1",
        entry_price=100.0,
        entry_type="CLOSE",
        fill_model="close",
        planned_stop_pct=0.10,
        planned_target_pct=0.20,
        planned_horizon_bars=2,
        decision_idx=0,
        frame=frame,
    )
    assert label.exit_reason == "TIME"
    assert label.hit_stop_before_target is True


def test_label_ambiguous_intrabar_assumes_stop_first():
    frame = _frame(
        [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100},
            {"Open": 100, "High": 106, "Low": 96, "Close": 100},
        ]
    )
    label = label_long_candidate(
        candidate_id="c4",
        label_version="labels_v1",
        entry_price=100.0,
        entry_type="CLOSE",
        fill_model="close",
        planned_stop_pct=0.03,
        planned_target_pct=0.04,
        planned_horizon_bars=1,
        decision_idx=0,
        frame=frame,
        ambiguous_intrabar_policy="assume_stop_first",
    )
    assert label.label_quality_flag == "AMBIGUOUS_INTRABAR"
    assert label.hit_stop is True
    assert label.exit_reason == "STOP"


def test_label_missing_forward_bars():
    frame = _frame([{"Open": 100, "High": 101, "Low": 99, "Close": 100}])
    label = label_long_candidate(
        candidate_id="c5",
        label_version="labels_v1",
        entry_price=100.0,
        entry_type="CLOSE",
        fill_model="close",
        planned_stop_pct=0.02,
        planned_target_pct=0.04,
        planned_horizon_bars=5,
        decision_idx=0,
        frame=frame,
    )
    assert label.label_quality_flag == "MISSING_BARS"


def test_label_next_open_entry():
    frame = _frame(
        [
            {"Open": 100, "High": 101, "Low": 99, "Close": 100},
            {"Open": 101, "High": 102, "Low": 96, "Close": 97},
            {"Open": 97, "High": 98, "Low": 95, "Close": 96},
        ]
    )
    label = label_long_candidate(
        candidate_id="c6",
        label_version="labels_v1",
        entry_price=100.0,
        entry_type="NEXT_OPEN",
        fill_model="close",
        planned_stop_pct=0.03,
        planned_target_pct=0.05,
        planned_horizon_bars=2,
        decision_idx=0,
        frame=frame,
    )
    assert label.entry_price == pytest.approx(101.0)
    assert label.hit_stop is True
