from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.config.models import AlpacaExecutionConfig, AlpacaTradingRunConfig
from app.live.executor import (
    AlpacaOpenOrder,
    AlpacaOrderResponse,
    AlpacaPosition,
    HttpAlpacaBarSource,
    RuntimeStateStore,
    build_alpaca_executor,
)
from app.strategies.core import Bar, PositionState, StrategyRuntimeSnapshot


BASE_TS = datetime(2024, 1, 1, 14, 30, tzinfo=UTC)


@dataclass
class FakeTradingClient:
    position: AlpacaPosition | None = None
    open_orders: list[AlpacaOpenOrder] | None = None
    response_status: str = "accepted"

    def __post_init__(self) -> None:
        self.submitted_orders: list[tuple[str, float, str, str]] = []
        if self.open_orders is None:
            self.open_orders = []

    def list_open_orders(self, symbol: str) -> list[AlpacaOpenOrder]:
        return list(self.open_orders or [])

    def get_position(self, symbol: str) -> AlpacaPosition | None:
        return self.position

    def submit_market_order(self, *, symbol: str, qty: float, side: str, client_order_id: str) -> AlpacaOrderResponse:
        self.submitted_orders.append((symbol, qty, side, client_order_id))
        order = AlpacaOpenOrder(client_order_id=client_order_id, side=side, status=self.response_status)
        self.open_orders = [*(self.open_orders or []), order]
        return AlpacaOrderResponse(id=f"id-{len(self.submitted_orders)}", client_order_id=client_order_id, status=self.response_status)


class FakeBarSource:
    def __init__(self, bars: list[Bar]):
        self.bars = bars

    def get_recent_bars(self, *, symbol: str, interval: str, feed: str, limit: int) -> list[Bar]:
        return self.bars[-limit:]


def _run(**overrides) -> AlpacaTradingRunConfig:
    payload = {
        "run_id": "live-demo",
        "symbol": "AAPL",
        "interval": "1m",
        "feed": "iex",
        "strategy": "buy_and_hold",
        "strategy_params": {"stake": 1},
    }
    payload.update(overrides)
    return AlpacaTradingRunConfig.model_validate(payload)


def _bars(*, closes: list[float], complete_flags: list[bool] | None = None) -> list[Bar]:
    flags = complete_flags or [True] * len(closes)
    return [
        Bar(
            timestamp=BASE_TS + timedelta(minutes=idx),
            open=close,
            high=close + 1,
            low=close - 1,
            close=close,
            volume=1000.0,
            is_complete=flags[idx],
        )
        for idx, close in enumerate(closes)
    ]


def test_executor_ignores_duplicate_completed_bar(tmp_path: Path):
    client = FakeTradingClient()
    bars = _bars(closes=[100, 101])
    executor = build_alpaca_executor(
        run=_run(),
        execution=AlpacaExecutionConfig(mode="paper", state_directory=str(tmp_path)),
        trading_client=client,
        bar_source=FakeBarSource(bars),
        state_store=RuntimeStateStore(str(tmp_path)),
    )

    executor.process_latest_bar()
    executor.process_latest_bar()

    assert len(client.submitted_orders) == 1


def test_executor_recovers_open_position_and_submits_close(tmp_path: Path):
    store = RuntimeStateStore(str(tmp_path))
    entry_bar = _bars(closes=[100, 98, 95])[0]
    store.save(
        "live-demo",
        StrategyRuntimeSnapshot(
            last_processed_bar_time=None,
            position=PositionState(
                is_open=True,
                size=1.0,
                entry_price=100.0,
                entry_bar_index=0,
                entry_time=entry_bar.iso_timestamp,
                bars_held=0,
            ),
            core_state={"has_entered": True},
        ),
    )
    client = FakeTradingClient(position=AlpacaPosition(symbol="AAPL", qty=1.0, avg_entry_price=100.0))
    bars = _bars(closes=[100, 98, 95])
    executor = build_alpaca_executor(
        run=_run(),
        execution=AlpacaExecutionConfig(mode="paper", state_directory=str(tmp_path)),
        trading_client=client,
        bar_source=FakeBarSource(bars),
        state_store=store,
    )

    executor.process_latest_bar()

    assert client.submitted_orders[-1][2] == "sell"


def test_executor_skips_resubmitting_when_open_order_already_exists(tmp_path: Path):
    bar = _bars(closes=[100, 101])[-1]
    order_id = f"live-demo-buy_and_hold-buy-{bar.timestamp.strftime('%Y%m%dT%H%M%S')}"
    client = FakeTradingClient(open_orders=[AlpacaOpenOrder(client_order_id=order_id, side="buy", status="accepted")])
    executor = build_alpaca_executor(
        run=_run(),
        execution=AlpacaExecutionConfig(mode="paper", state_directory=str(tmp_path)),
        trading_client=client,
        bar_source=FakeBarSource(_bars(closes=[100, 101])),
        state_store=RuntimeStateStore(str(tmp_path)),
    )

    executor.process_latest_bar()

    assert client.submitted_orders == []


def test_executor_returns_rejected_order_event(tmp_path: Path):
    client = FakeTradingClient(response_status="rejected")
    executor = build_alpaca_executor(
        run=_run(),
        execution=AlpacaExecutionConfig(mode="paper", state_directory=str(tmp_path)),
        trading_client=client,
        bar_source=FakeBarSource(_bars(closes=[100, 101])),
        state_store=RuntimeStateStore(str(tmp_path)),
    )

    events = executor.process_latest_bar()

    assert len(events) == 1
    assert events[0].event_type == "order_rejected"
    assert events[0].status == "rejected"


def test_build_executor_uses_requested_mode(monkeypatch, tmp_path: Path):
    captured: dict[str, str] = {}

    class FakeHttpClient:
        def __init__(self, mode: str):
            captured["mode"] = mode

        def list_open_orders(self, symbol: str):
            return []

        def get_position(self, symbol: str):
            return None

        def submit_market_order(self, *, symbol: str, qty: float, side: str, client_order_id: str):
            raise AssertionError("should not submit in this test")

    class FakeHttpBarSource:
        def get_recent_bars(self, *, symbol: str, interval: str, feed: str, limit: int):
            return []

    monkeypatch.setattr("app.live.executor.HttpAlpacaTradingClient", FakeHttpClient)
    monkeypatch.setattr("app.live.executor.HttpAlpacaBarSource", FakeHttpBarSource)

    build_alpaca_executor(
        run=_run(),
        execution=AlpacaExecutionConfig(mode="live", state_directory=str(tmp_path)),
        state_store=RuntimeStateStore(str(tmp_path)),
    )

    assert captured["mode"] == "live"


def test_paper_trading_smoke_ignores_incomplete_then_does_not_double_enter_after_restart(tmp_path: Path):
    store = RuntimeStateStore(str(tmp_path))
    client = FakeTradingClient()
    incomplete_bars = _bars(closes=[100, 101], complete_flags=[True, False])
    executor = build_alpaca_executor(
        run=_run(),
        execution=AlpacaExecutionConfig(mode="paper", state_directory=str(tmp_path)),
        trading_client=client,
        bar_source=FakeBarSource(incomplete_bars),
        state_store=store,
    )

    events = executor.process_latest_bar()
    assert events == []
    assert client.submitted_orders == []

    complete_bars = _bars(closes=[100, 101], complete_flags=[True, True])
    executor = build_alpaca_executor(
        run=_run(),
        execution=AlpacaExecutionConfig(mode="paper", state_directory=str(tmp_path)),
        trading_client=client,
        bar_source=FakeBarSource(complete_bars),
        state_store=store,
    )
    executor.process_latest_bar()
    assert len(client.submitted_orders) == 1

    restarted = build_alpaca_executor(
        run=_run(),
        execution=AlpacaExecutionConfig(mode="paper", state_directory=str(tmp_path)),
        trading_client=client,
        bar_source=FakeBarSource(complete_bars),
        state_store=store,
    )
    restarted.process_latest_bar()
    assert len(client.submitted_orders) == 1
