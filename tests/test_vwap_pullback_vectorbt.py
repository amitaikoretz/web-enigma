from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from app.strategies.components import ComposableStrategyCore
from app.strategies.factory import build_strategy_core
from app.strategies.exit_rules import ExitRulesSelection
from app.strategies.vectorbt_support import VectorbtBuildContext, build_portfolio_from_spec
from app.strategies.yaml_io import load_exit_rules_selection, load_trigger_selection


REPO_ROOT = Path(__file__).resolve().parents[1]
US_EASTERN = ZoneInfo("America/New_York")


def _make_intraday_frame(
    *,
    start_price: float = 100.0,
    close_step: float = 0.1,
    volume_base: float = 1000.0,
    entry_index: int = 8,
    trim_index: int = 9,
    total_bars: int = 12,
    start_time: datetime | None = None,
) -> pd.DataFrame:
    start = start_time or datetime(2024, 1, 2, 9, 30, tzinfo=US_EASTERN)
    rows: list[dict[str, object]] = []
    for idx in range(total_bars):
        close = start_price + idx * close_step
        if idx == entry_index:
            close = 102.4
        if idx == trim_index:
            close = 104.0
        if rows and idx > trim_index:
            close = max(close, float(rows[-1]["Close"]) + 0.03)
        open_price = close - 0.04
        high = close + 0.05
        low = close - 0.08
        volume = volume_base + idx * 25
        if idx == entry_index:
            open_price = float(rows[-1]["Close"]) + 0.01 if rows else close - 0.04
            high = close + 0.04
            low = 100.95
            volume = volume_base * 3
        if idx == trim_index:
            open_price = float(rows[-1]["Close"]) + 0.02 if rows else close - 0.04
            high = close + 0.18
            low = close - 0.15
            volume = volume_base * 2.5
        rows.append(
            {
                "datetime": start + timedelta(minutes=5 * idx),
                "Open": open_price,
                "High": high,
                "Low": low,
                "Close": close,
                "Volume": volume,
            }
        )
    frame = pd.DataFrame(rows).set_index("datetime")
    frame.index = pd.DatetimeIndex(frame.index)
    return frame


def _make_benchmark_frame(
    *,
    total_bars: int = 12,
    start_price: float = 200.0,
    close_step: float = 0.1,
    volume_base: float = 2000.0,
    start_time: datetime | None = None,
) -> pd.DataFrame:
    start = start_time or datetime(2024, 1, 2, 9, 30, tzinfo=US_EASTERN)
    rows: list[dict[str, object]] = []
    for idx in range(total_bars):
        close = start_price + idx * close_step
        rows.append(
            {
                "datetime": start + timedelta(minutes=5 * idx),
                "Open": close - 0.03,
                "High": close + 0.05,
                "Low": close - 0.05,
                "Close": close,
                "Volume": volume_base + idx * 10,
            }
        )
    frame = pd.DataFrame(rows).set_index("datetime")
    frame.index = pd.DatetimeIndex(frame.index)
    return frame


def _build_vwap_core() -> ComposableStrategyCore:
    trigger = load_trigger_selection(
        str(REPO_ROOT / "examples/triggers/vwap_pullback.yaml"),
        base_dir=REPO_ROOT,
    )
    exit_rules = load_exit_rules_selection(
        str(REPO_ROOT / "examples/exit_rules/vwap_pullback_manage.yaml"),
        base_dir=REPO_ROOT,
    )
    return build_strategy_core(trigger=trigger, exit_rules=exit_rules)


def _build_vectorbt_ready_vwap_core(exit_rule_updates: dict[str, int] | None = None) -> ComposableStrategyCore:
    trigger = load_trigger_selection(str(REPO_ROOT / "examples/triggers/vwap_pullback.yaml"), base_dir=REPO_ROOT)
    exit_rules = load_exit_rules_selection(str(REPO_ROOT / "examples/exit_rules/vwap_pullback_manage.yaml"), base_dir=REPO_ROOT)
    trigger.params.update(
        {
            "trend_ema_fast": 2,
            "trend_ema_mid": 3,
            "trend_ema_slow": 4,
            "benchmark_ema_fast": 2,
            "benchmark_ema_slow": 3,
            "benchmark_resolution_minutes": 15,
            "volume_window": 3,
            "volume_spike_mult": 1.1,
            "pullback_distance_pct": 0.01,
            "recent_close_window": 3,
            "min_closes_above_vwap": 1,
            "max_entry_gap_pct": 0.01,
            "max_stop_distance_pct": 0.05,
            "max_stop_atr_mult": 10.0,
            "session_morning_start_minutes": 0,
            "session_morning_end_minutes": 390,
            "session_afternoon_start_minutes": 0,
            "session_afternoon_end_minutes": 390,
        }
    )
    if exit_rule_updates:
        exit_rules.rules[0].params.update(exit_rule_updates)
    return build_strategy_core(trigger=trigger, exit_rules=exit_rules)


def _vectorbt_context(
    main_frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame | None = None,
) -> VectorbtBuildContext:
    return VectorbtBuildContext(data=main_frame, benchmark_data=benchmark_frame, params={}, shared={})


def test_vwap_pullback_vectorbt_spec_emits_single_entry_trim_and_exit():
    core = _build_vectorbt_ready_vwap_core()
    main_frame = _make_intraday_frame(total_bars=78, entry_index=23, trim_index=24)
    benchmark_frame = _make_benchmark_frame(total_bars=78)
    spec = core.vectorbt_spec(_vectorbt_context(main_frame, benchmark_frame))

    assert spec is not None
    assert int(spec.entries.sum()) == 1
    assert int(spec.trim_exits.sum()) == 1
    assert int(spec.exits.sum()) == 1
    assert bool(spec.entries.iloc[23]) is True
    assert bool(spec.trim_exits.iloc[24]) is True
    assert bool(spec.exits.iloc[35]) is True


def test_vwap_pullback_vectorbt_portfolio_builds_expected_orders():
    core = _build_vectorbt_ready_vwap_core()
    main_frame = _make_intraday_frame(total_bars=78, entry_index=23, trim_index=24)
    benchmark_frame = _make_benchmark_frame(total_bars=78)
    context = _vectorbt_context(main_frame, benchmark_frame)
    spec = core.vectorbt_spec(context)

    assert spec is not None
    portfolio = build_portfolio_from_spec(spec, context, init_cash=100_000.0, fill_model="next_bar", freq="5min")
    orders = portfolio.orders.records_readable

    assert portfolio.orders.count() == 3
    assert orders["Side"].tolist() == ["Buy", "Sell", "Sell"]
    assert orders["Size"].tolist() == [10.0, 5.0, 5.0]


def test_vwap_pullback_vectorbt_spec_does_not_depend_on_frame_to_bars(monkeypatch: pytest.MonkeyPatch):
    core = _build_vectorbt_ready_vwap_core()
    main_frame = _make_intraday_frame(total_bars=78, entry_index=23, trim_index=24)
    benchmark_frame = _make_benchmark_frame(total_bars=78)

    def _boom(*args, **kwargs):
        raise AssertionError("frame_to_bars should not be called by VwapPullbackTrigger.vectorbt_spec")

    monkeypatch.setattr("app.strategies.vectorbt_support.frame_to_bars", _boom)

    spec = core.vectorbt_spec(_vectorbt_context(main_frame, benchmark_frame))

    assert spec is not None
    assert int(spec.entries.sum()) == 1
    assert int(spec.trim_exits.sum()) == 1
    assert int(spec.exits.sum()) == 1


@pytest.mark.parametrize(
    "gate_name, mutate, trigger_updates",
    [
        (
            "benchmark",
            lambda frame: None,
            {"benchmark_step": -0.1},
        ),
        (
            "volume",
            lambda frame: frame.assign(Volume=1000.0),
            {"volume_spike_mult": 10.0},
        ),
        (
            "session",
            lambda frame: None,
            {
                "session_morning_start_minutes": 400,
                "session_morning_end_minutes": 500,
                "session_afternoon_start_minutes": 400,
                "session_afternoon_end_minutes": 500,
            },
        ),
    ],
)
def test_vwap_pullback_vectorbt_rejects_entry_gates(gate_name: str, mutate, trigger_updates):
    main_frame = _make_intraday_frame(total_bars=78, entry_index=23, trim_index=24)
    benchmark_step = -0.1 if gate_name == "benchmark" else 0.1
    benchmark_frame = _make_benchmark_frame(total_bars=78, close_step=benchmark_step)
    if gate_name == "volume":
        main_frame = mutate(main_frame)

    trigger = load_trigger_selection(str(REPO_ROOT / "examples/triggers/vwap_pullback.yaml"), base_dir=REPO_ROOT)
    exit_rules = load_exit_rules_selection(str(REPO_ROOT / "examples/exit_rules/vwap_pullback_manage.yaml"), base_dir=REPO_ROOT)
    trigger_kwargs = {
        "trend_ema_fast": 2,
        "trend_ema_mid": 3,
        "trend_ema_slow": 4,
        "benchmark_ema_fast": 2,
        "benchmark_ema_slow": 3,
        "benchmark_resolution_minutes": 15,
        "volume_window": 3,
        "volume_spike_mult": 1.1,
        "pullback_distance_pct": 0.01,
        "recent_close_window": 3,
        "min_closes_above_vwap": 1,
        "max_entry_gap_pct": 0.01,
        "max_stop_distance_pct": 0.05,
        "max_stop_atr_mult": 10.0,
        "session_morning_start_minutes": 0,
        "session_morning_end_minutes": 390,
        "session_afternoon_start_minutes": 0,
        "session_afternoon_end_minutes": 390,
    }
    if gate_name == "volume":
        trigger_kwargs["volume_spike_mult"] = 10.0
    elif gate_name == "session":
        trigger_kwargs["session_morning_start_minutes"] = 400
        trigger_kwargs["session_morning_end_minutes"] = 500
        trigger_kwargs["session_afternoon_start_minutes"] = 400
        trigger_kwargs["session_afternoon_end_minutes"] = 500
    trigger.params.update(trigger_kwargs)
    core = build_strategy_core(trigger=trigger, exit_rules=exit_rules)
    spec = core.vectorbt_spec(_vectorbt_context(main_frame, benchmark_frame))

    assert spec is not None
    assert int(spec.entries.sum()) == 0


def test_existing_vectorbt_strategies_still_build_with_extended_spec_shape():
    trigger = load_trigger_selection(str(REPO_ROOT / "examples/triggers/buy_and_hold.yaml"), base_dir=REPO_ROOT)
    exit_rules = ExitRulesSelection.model_validate(
        {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 2}}]}
    )
    core = build_strategy_core(trigger=trigger, exit_rules=exit_rules)
    data = _make_intraday_frame(total_bars=4)
    context = _vectorbt_context(data, None)
    spec = core.vectorbt_spec(context)

    assert spec is not None
    assert spec.trim_exits is None
    assert spec.entries is not None
