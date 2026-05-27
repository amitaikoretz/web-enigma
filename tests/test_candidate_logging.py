from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.config.models import AlpacaExecutionConfig, AlpacaTradingRunConfig
from app.engine.metrics import build_candidate_records, compute_candidate_diagnostics
from app.live.executor import RuntimeStateStore, build_alpaca_executor
from app.output.models import CandidateRecord
from app.strategies.candidates import EntryIntent, finalize_candidate, make_candidate_id, record_candidate
from app.strategies.core import Bar, StrategyContext, StrategyDecision
from app.strategies.entry_plans import atr_entry_intent, fixed_pct_entry_intent
from app.strategies.implementations import BreakoutChannelCore, VolumeRallyCore


def _bar(close: float = 100.0, *, high: float | None = None, low: float | None = None, volume: float = 1_000_000.0) -> Bar:
    return Bar(
        timestamp=datetime(2026, 5, 6, 14, 45, tzinfo=UTC),
        open=close - 0.5,
        high=high if high is not None else close + 1.0,
        low=low if low is not None else close - 1.0,
        close=close,
        volume=volume,
    )


def _context(*bars: Bar, symbol: str = "AAPL") -> StrategyContext:
    history = bars if bars else (_bar(),)
    return StrategyContext(
        bar=history[-1],
        bars=tuple(history),
        position=__import__("app.strategies.core", fromlist=["PositionState"]).PositionState(),
        symbol=symbol,
        equity=10_000.0,
    )


def test_make_candidate_id_is_deterministic():
    first = make_candidate_id(strategy_id="volume_rally", symbol="AAPL", timestamp="2026-05-06T14:45:00+00:00", side="LONG")
    second = make_candidate_id(strategy_id="volume_rally", symbol="AAPL", timestamp="2026-05-06T14:45:00+00:00", side="LONG")
    assert first == second
    assert len(first) == 16


def test_finalize_candidate_marks_traded_and_rejected():
    intent = EntryIntent(
        entry_price=100.0,
        planned_stop_pct=0.02,
        planned_target_pct=0.04,
        planned_horizon_bars=10,
        signal_score=0.8,
        signal_reason="breakout",
    )
    traded = finalize_candidate(
        StrategyDecision.buy(1.0, "breakout", entry_intent=intent),
        strategy_id="breakout_channel",
        symbol="AAPL",
        timestamp="2026-05-06T14:45:00+00:00",
        entry_type="CLOSE",
    )
    rejected = finalize_candidate(
        StrategyDecision.hold("session_window", auditor_rejection=True, entry_intent=intent),
        strategy_id="breakout_channel",
        symbol="AAPL",
        timestamp="2026-05-06T14:45:00+00:00",
        entry_type="CLOSE",
    )
    assert traded is not None and traded.was_traded is True and traded.reject_reason is None
    assert rejected is not None and rejected.was_traded is False and rejected.reject_reason == "session_window"


def test_record_candidate_noop_when_disabled():
    intent = EntryIntent(
        entry_price=100.0,
        planned_stop_pct=0.02,
        planned_target_pct=0.04,
        planned_horizon_bars=10,
    )
    decision = StrategyDecision.buy(1.0, entry_intent=intent)
    log: list = []
    event = record_candidate(
        log,
        decision,
        enabled=False,
        strategy_id="breakout_channel",
        symbol="AAPL",
        timestamp="2026-05-06T14:45:00+00:00",
        entry_type="CLOSE",
    )
    assert event is None
    assert log == []


def test_fixed_pct_and_atr_entry_intent_math():
    context = _context(_bar(100.0))
    fixed = fixed_pct_entry_intent(
        context,
        {"stop_loss_pct": 0.02, "take_profit_pct": 0.04, "max_hold_bars": 12},
        signal_score=1.0,
        signal_reason="breakout",
    )
    assert fixed.planned_stop_pct == pytest.approx(0.02)
    assert fixed.planned_target_pct == pytest.approx(0.04)
    assert fixed.planned_horizon_bars == 12

    atr = atr_entry_intent(
        100.0,
        2.0,
        sl_mult=1.5,
        tp_mult=3.0,
        horizon_bars=20,
        signal_score=0.5,
        signal_reason="volume_rally",
    )
    assert atr.planned_stop_pct == pytest.approx(0.03)
    assert atr.planned_target_pct == pytest.approx(0.06)


def test_breakout_channel_attaches_entry_intent_on_signal():
    bars = [_bar(90.0 + index, high=91.0 + index) for index in range(24)]
    bars.append(_bar(115.0, high=116.0))
    context = _context(*bars)
    core = BreakoutChannelCore({"lookback": 5, "stake": 1.0, "stop_loss_pct": 0.01, "take_profit_pct": 0.02, "max_hold_bars": 10})
    decision = core.on_bar(context)
    assert decision.action == "buy"
    assert decision.entry_intent is not None
    assert decision.entry_intent.planned_stop_pct == pytest.approx(0.01)


def test_volume_rally_attaches_entry_intent_on_rejected_signal():
    from test_strategy_core import _context, _volume_rally_breakout_bars, _volume_rally_params

    core = VolumeRallyCore(_volume_rally_params(min_confirmations=2, session_start_minutes=9999))
    decision = core.on_bar(_context(_volume_rally_breakout_bars()))
    assert decision.action == "hold"
    assert decision.entry_intent is not None
    assert decision.reason == "session_window"
    assert decision.entry_intent.signal_reason == "volume_rally"


def test_volume_rally_logs_partial_confirmation_as_rejected_candidate():
    from test_strategy_core import _context, _volume_rally_breakout_bars, _volume_rally_params

    core = VolumeRallyCore(
        _volume_rally_params(
            min_confirmations=6,
            adx_min=101.0,
            session_start_minutes=0,
            session_end_minutes=0,
        )
    )
    decision = core.on_bar(_context(_volume_rally_breakout_bars()))
    assert decision.action == "hold"
    assert decision.reason == "insufficient_confirmations"
    assert decision.entry_intent is not None
    rejected = finalize_candidate(
        decision,
        strategy_id="volume_rally",
        symbol="AAPL",
        timestamp="2026-05-06T14:45:00+00:00",
        entry_type="CLOSE",
    )
    assert rejected is not None
    assert rejected.was_traded is False
    assert rejected.reject_reason == "insufficient_confirmations"


def test_portable_strategy_accumulates_candidates_only_when_enabled():
    intent = EntryIntent(
        entry_price=100.0,
        planned_stop_pct=0.01,
        planned_target_pct=0.02,
        planned_horizon_bars=5,
        signal_score=1.0,
        signal_reason="test",
    )
    decision = StrategyDecision.buy(1.0, "test", entry_intent=intent)
    enabled_log: list = []
    disabled_log: list = []
    record_candidate(
        enabled_log,
        decision,
        enabled=True,
        strategy_id="test_strategy",
        symbol="AAPL",
        timestamp="2026-05-06T14:45:00+00:00",
        entry_type="CLOSE",
    )
    record_candidate(
        disabled_log,
        decision,
        enabled=False,
        strategy_id="test_strategy",
        symbol="AAPL",
        timestamp="2026-05-06T14:45:00+00:00",
        entry_type="CLOSE",
    )
    assert len(enabled_log) == 1
    assert disabled_log == []


def test_build_candidate_records_and_diagnostics():
    from app.strategies.candidates import CandidateEvent

    event = CandidateEvent(
        candidate_id="abc123",
        strategy_id="breakout_channel",
        symbol="AAPL",
        timestamp="2026-05-06T14:45:00+00:00",
        entry_price=100.0,
        planned_stop_pct=0.01,
        planned_target_pct=0.02,
        planned_horizon_bars=10,
        was_traded=True,
    )
    records = build_candidate_records([event])
    diagnostics = compute_candidate_diagnostics(records)
    assert len(records) == 1
    assert isinstance(records[0], CandidateRecord)
    assert diagnostics.total_candidates == 1
    assert diagnostics.traded_candidates == 1
    assert diagnostics.rejected_candidates == 0


def test_backtest_runner_persists_candidates_when_enabled():
    from app.config.models import BacktestConfig
    from app.engine.runner import run_backtests

    raw = {
        "runs": [
            {
                "run_id": "csv_candidates",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategy": "breakout_channel",
                "strategy_params": {
                    "lookback": 3,
                    "stake": 1.0,
                    "stop_loss_pct": 0.01,
                    "take_profit_pct": 0.02,
                    "max_hold_bars": 5,
                },
                "analyzers": {"include_candidate_log": True},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.successful_runs == 1
    result = report.results[0]
    assert len(result.candidates) >= 1
    assert result.analyzers["candidate_diagnostics"]["total_candidates"] == len(result.candidates)


class _FakeTradingClient:
    def list_open_orders(self, symbol: str):
        return []

    def get_position(self, symbol: str):
        return None

    def submit_market_order(self, *, symbol: str, qty: float, side: str, client_order_id: str):
        return type("Resp", (), {"id": "1", "client_order_id": client_order_id, "status": "accepted"})()


class _FakeBarSource:
    def get_recent_bars(self, *, symbol: str, interval: str, feed: str, limit: int):
        return [
            Bar(
                timestamp=datetime(2026, 5, 6, 14, 40, tzinfo=UTC),
                open=99.0,
                high=101.0,
                low=98.5,
                close=100.0,
                volume=1_000_000.0,
                is_complete=True,
            ),
            Bar(
                timestamp=datetime(2026, 5, 6, 14, 45, tzinfo=UTC),
                open=100.0,
                high=102.0,
                low=99.5,
                close=101.0,
                volume=2_000_000.0,
                is_complete=True,
            ),
        ]


class _SignalCore:
    def load_state(self, state):
        return None

    def dump_state(self):
        return {}

    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        intent = fixed_pct_entry_intent(
            context,
            {"stop_loss_pct": 0.01, "take_profit_pct": 0.02, "max_hold_bars": 5},
            signal_score=1.0,
            signal_reason="test",
        )
        return StrategyDecision.hold("session_window", auditor_rejection=True, entry_intent=intent)


def test_live_executor_writes_candidate_jsonl(tmp_path: Path):
    run = AlpacaTradingRunConfig(
        run_id="run-1",
        symbol="AAPL",
        strategy="breakout_channel",
        strategy_params={"lookback": 5, "stake": 1.0, "stop_loss_pct": 0.01, "take_profit_pct": 0.02, "max_hold_bars": 10},
    )
    execution = AlpacaExecutionConfig(state_directory=str(tmp_path), include_candidate_log=True)
    executor = build_alpaca_executor(
        run=run,
        execution=execution,
        trading_client=_FakeTradingClient(),
        bar_source=_FakeBarSource(),
        state_store=RuntimeStateStore(str(tmp_path / "state")),
        include_candidate_log=True,
    )
    executor.core = _SignalCore()
    executor.process_latest_bar()
    candidate_path = tmp_path / "run-1" / "candidates.jsonl"
    assert candidate_path.exists()
    lines = candidate_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["symbol"] == "AAPL"
    assert payload["was_traded"] is False
    assert payload["reject_reason"] == "session_window"
