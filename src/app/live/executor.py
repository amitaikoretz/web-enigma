from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.config.models import AlpacaExecutionConfig, AlpacaTradingRunConfig
from app.alpaca_transport import alpaca_transport_failure_label
from app.alpaca_transport import format_alpaca_transport_failure_message
from app.alpaca_transport import is_temporary_alpaca_transport_failure
from app.strategies.candidates import CandidateEvent, record_candidate
from app.strategies.core import Bar, ExecutionEvent, PositionState, StrategyContext, StrategyCore, StrategyRuntimeSnapshot
from app.strategies.auditor_logging import log_auditor_rejection
from app.strategies.implementations import _benchmark_bars_as_of
from app.strategies.factory import build_strategy_core, composed_strategy_id, resolve_warmup_bars

logger = logging.getLogger(__name__)


def _sleep_backoff(attempt_index: int, *, base_s: float = 1.0, cap_s: float = 30.0) -> float:
    delay = min(cap_s, base_s * (2**attempt_index))
    jitter = random.uniform(0.0, min(1.0, delay * 0.2))
    time.sleep(delay + jitter)
    return delay + jitter


@dataclass(frozen=True)
class AlpacaOpenOrder:
    client_order_id: str
    side: str
    status: str


@dataclass(frozen=True)
class AlpacaPosition:
    symbol: str
    qty: float
    avg_entry_price: float


@dataclass(frozen=True)
class AlpacaOrderResponse:
    id: str
    client_order_id: str
    status: str


class AlpacaTradingClient(Protocol):
    def list_open_orders(self, symbol: str) -> list[AlpacaOpenOrder]: ...

    def get_position(self, symbol: str) -> AlpacaPosition | None: ...

    def submit_market_order(self, *, symbol: str, qty: float, side: str, client_order_id: str) -> AlpacaOrderResponse: ...


class AlpacaBarSource(Protocol):
    def get_recent_bars(self, *, symbol: str, interval: str, feed: str, limit: int) -> list[Bar]: ...


class RuntimeStateStore:
    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, run_id: str) -> Path:
        return self.directory / f"{run_id}.json"

    def load(self, run_id: str) -> StrategyRuntimeSnapshot:
        path = self._path(run_id)
        if not path.exists():
            return StrategyRuntimeSnapshot()
        payload = json.loads(path.read_text(encoding="utf-8"))
        position_payload = payload.get("position", {})
        position = PositionState(**position_payload) if position_payload else PositionState()
        return StrategyRuntimeSnapshot(
            last_processed_bar_time=payload.get("last_processed_bar_time"),
            position=position,
            core_state=payload.get("core_state", {}),
        )

    def save(self, run_id: str, snapshot: StrategyRuntimeSnapshot) -> None:
        payload = {
            "last_processed_bar_time": snapshot.last_processed_bar_time,
            "position": asdict(snapshot.position),
            "core_state": snapshot.core_state,
        }
        self._path(run_id).write_text(json.dumps(payload, indent=2), encoding="utf-8")


class HttpAlpacaTradingClient:
    def __init__(self, mode: str):
        key = os.environ.get("ALPACA_API_KEY")
        secret = os.environ.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("Alpaca credentials missing: set ALPACA_API_KEY and ALPACA_SECRET_KEY")
        self._key = key
        self._secret = secret
        self._base_url = "https://paper-api.alpaca.markets" if mode == "paper" else "https://api.alpaca.markets"

    def _request(self, method: str, path: str, params: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> Any:
        url = f"{self._base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        payload = None if body is None else json.dumps(body).encode("utf-8")
        req = Request(
            url,
            data=payload,
            method=method,
            headers={
                "APCA-API-KEY-ID": self._key,
                "APCA-API-SECRET-KEY": self._secret,
                "accept": "application/json",
                "content-type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Alpaca trading request failed ({exc.code}): {body or exc.reason}") from exc
        except URLError as exc:
            raise RuntimeError(format_alpaca_transport_failure_message(service="trading API", exc=exc)) from exc

    def list_open_orders(self, symbol: str) -> list[AlpacaOpenOrder]:
        payload = self._request("GET", "/v2/orders", params={"status": "open", "symbols": symbol})
        return [
            AlpacaOpenOrder(
                client_order_id=str(item.get("client_order_id", "")),
                side=str(item.get("side", "")),
                status=str(item.get("status", "")),
            )
            for item in payload
        ]

    def get_position(self, symbol: str) -> AlpacaPosition | None:
        try:
            payload = self._request("GET", f"/v2/positions/{symbol}")
        except RuntimeError as exc:
            if "404" in str(exc):
                return None
            raise
        if not payload:
            return None
        return AlpacaPosition(
            symbol=str(payload.get("symbol", symbol)),
            qty=float(payload.get("qty", 0.0) or 0.0),
            avg_entry_price=float(payload.get("avg_entry_price", 0.0) or 0.0),
        )

    def submit_market_order(self, *, symbol: str, qty: float, side: str, client_order_id: str) -> AlpacaOrderResponse:
        payload = self._request(
            "POST",
            "/v2/orders",
            body={
                "symbol": symbol,
                "qty": str(qty),
                "side": side,
                "type": "market",
                "time_in_force": "day",
                "client_order_id": client_order_id,
            },
        )
        return AlpacaOrderResponse(
            id=str(payload.get("id", "")),
            client_order_id=str(payload.get("client_order_id", client_order_id)),
            status=str(payload.get("status", "accepted")),
        )


class HttpAlpacaBarSource:
    def __init__(self):
        key = os.environ.get("ALPACA_API_KEY")
        secret = os.environ.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise RuntimeError("Alpaca credentials missing: set ALPACA_API_KEY and ALPACA_SECRET_KEY")
        self._key = key
        self._secret = secret
        self._base_url = "https://data.alpaca.markets"

    def get_recent_bars(self, *, symbol: str, interval: str, feed: str, limit: int) -> list[Bar]:
        timeframe = _alpaca_timeframe(interval)
        req = Request(
            f"{self._base_url}/v2/stocks/{symbol}/bars?{urlencode({'timeframe': timeframe, 'limit': str(limit), 'feed': feed, 'sort': 'asc', 'adjustment': 'raw'})}",
            headers={
                "APCA-API-KEY-ID": self._key,
                "APCA-API-SECRET-KEY": self._secret,
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
                raise RuntimeError(f"Alpaca data request failed ({exc.code}): {body or exc.reason}") from exc
            except URLError as exc:
                last_exc = exc
                if not is_temporary_alpaca_transport_failure(exc) or attempt == 5:
                    raise RuntimeError(format_alpaca_transport_failure_message(service="data API", exc=exc)) from exc
                delay_s = _sleep_backoff(attempt)
                logger.warning(
                    "Alpaca transport failure (%s). Retrying in %.2fs (attempt %d/%d). Error=%r",
                    alpaca_transport_failure_label(exc),
                    delay_s,
                    attempt + 1,
                    6,
                    exc.reason,
                )
        if last_exc is not None:
            raise RuntimeError(format_alpaca_transport_failure_message(service="data API", exc=last_exc)) from last_exc

        bars: list[Bar] = []
        now = datetime.now(UTC)
        delta = _interval_to_timedelta(interval)
        for item in payload.get("bars") or []:
            ts = datetime.fromisoformat(str(item["t"]).replace("Z", "+00:00"))
            bars.append(
                Bar(
                    timestamp=ts,
                    open=float(item["o"]),
                    high=float(item["h"]),
                    low=float(item["l"]),
                    close=float(item["c"]),
                    volume=float(item.get("v", 0.0) or 0.0),
                    is_complete=now >= ts + delta,
                )
            )
        return bars


class AlpacaStrategyExecutor:
    def __init__(
        self,
        *,
        run: AlpacaTradingRunConfig,
        execution: AlpacaExecutionConfig,
        trading_client: AlpacaTradingClient,
        bar_source: AlpacaBarSource,
        state_store: RuntimeStateStore,
    ):
        self.run = run
        self.execution = execution
        self.trading_client = trading_client
        self.bar_source = bar_source
        self.state_store = state_store
        if run.trigger is None or run.exit_rules is None:
            raise ValueError("Live run is missing trigger/exit rules selection")
        self.strategy_id = composed_strategy_id(trigger=run.trigger, exit_rules=run.exit_rules)
        self.core: StrategyCore = build_strategy_core(trigger=run.trigger, exit_rules=run.exit_rules)
        self.warmup_bars = max(2, resolve_warmup_bars(trigger=run.trigger, exit_rules=run.exit_rules))
        self.snapshot = self.state_store.load(run.run_id)
        self.core.load_state(self.snapshot.core_state)
        self.seen_client_order_ids = {order.client_order_id for order in self.trading_client.list_open_orders(run.symbol)}
        self.candidate_log: list[CandidateEvent] = []
        self._candidate_log_path = (
            Path(execution.state_directory) / run.run_id / "candidates.jsonl"
        )
        self._sync_position_from_broker()

    def _persist_candidate(self, event: CandidateEvent) -> None:
        self._candidate_log_path.parent.mkdir(parents=True, exist_ok=True)
        with self._candidate_log_path.open("a", encoding="utf-8") as handle:
            handle.write(event.model_dump_json())
            handle.write("\n")

    def _sync_position_from_broker(self) -> None:
        live_position = self.trading_client.get_position(self.run.symbol)
        if live_position is None or live_position.qty == 0:
            self.snapshot = StrategyRuntimeSnapshot(
                last_processed_bar_time=self.snapshot.last_processed_bar_time,
                position=PositionState(),
                core_state=self.core.dump_state(),
            )
            return

        current = self.snapshot.position
        self.snapshot = StrategyRuntimeSnapshot(
            last_processed_bar_time=self.snapshot.last_processed_bar_time,
            position=PositionState(
                is_open=True,
                size=float(live_position.qty),
                entry_price=float(live_position.avg_entry_price),
                entry_bar_index=current.entry_bar_index,
                entry_time=current.entry_time,
                bars_held=current.bars_held,
            ),
            core_state=self.core.dump_state(),
        )

    def _position_for_history(self, bars: list[Bar]) -> PositionState:
        position = self.snapshot.position
        if not position.is_open:
            return PositionState()
        entry_bar_index = position.entry_bar_index
        if entry_bar_index is None and position.entry_time:
            for idx, bar in enumerate(bars):
                if bar.iso_timestamp == position.entry_time:
                    entry_bar_index = idx
                    break
        if entry_bar_index is None:
            bars_held = 0
        else:
            bars_held = max(0, len(bars) - 1 - entry_bar_index)
        return PositionState(
            is_open=True,
            size=position.size,
            entry_price=position.entry_price,
            entry_bar_index=entry_bar_index,
            entry_time=position.entry_time,
            bars_held=bars_held,
        )

    def _client_order_id(self, action: str, bar: Bar) -> str:
        return f"{self.run.run_id}-{self.strategy_id}-{action}-{bar.timestamp.strftime('%Y%m%dT%H%M%S')}"

    def _save_snapshot(self) -> None:
        self.snapshot = StrategyRuntimeSnapshot(
            last_processed_bar_time=self.snapshot.last_processed_bar_time,
            position=self.snapshot.position,
            core_state=self.core.dump_state(),
        )
        self.state_store.save(self.run.run_id, self.snapshot)

    def process_latest_bar(self) -> list[ExecutionEvent]:
        bars = self.bar_source.get_recent_bars(
            symbol=self.run.symbol,
            interval=self.run.interval,
            feed=self.run.feed,
            limit=self.warmup_bars + 2,
        )
        if not bars or not bars[-1].is_complete:
            return []
        complete_bars = [bar for bar in bars if bar.is_complete]
        if not complete_bars:
            return []

        latest = complete_bars[-1]
        if self.snapshot.last_processed_bar_time == latest.iso_timestamp:
            return []

        self._sync_position_from_broker()
        position = self._position_for_history(complete_bars)
        benchmark_symbol = str(self.run.trigger.params.get("benchmark_symbol", "")).strip().upper() if self.run.trigger else ""
        benchmark_bars: tuple[Bar, ...] | None = None
        if benchmark_symbol:
            raw_benchmark_bars = self.bar_source.get_recent_bars(
                symbol=benchmark_symbol,
                interval=self.run.interval,
                feed=self.run.feed,
                limit=self.warmup_bars + 2,
            )
            complete_benchmark_bars = tuple(bar for bar in raw_benchmark_bars if bar.is_complete)
            benchmark_bars = _benchmark_bars_as_of(latest, complete_benchmark_bars) if complete_benchmark_bars else None
        context = StrategyContext(
            bar=latest,
            bars=tuple(complete_bars),
            position=position,
            symbol=self.run.symbol,
            equity=None,
            benchmark_bars=benchmark_bars,
        )
        decision = self.core.on_bar(context)
        events: list[ExecutionEvent] = []

        candidate_event = record_candidate(
            self.candidate_log,
            decision,
            enabled=self.execution.include_candidate_log,
            strategy_id=self.strategy_id,
            symbol=self.run.symbol,
            timestamp=latest.iso_timestamp,
            entry_type="MARKET",
        )
        if candidate_event is not None and self.execution.include_candidate_log:
            self._persist_candidate(candidate_event)

        if decision.action == "hold" and decision.auditor_rejection:
            log_auditor_rejection(
                symbol=self.run.symbol,
                timestamp=latest.iso_timestamp,
                reason=decision.reason,
            )

        if decision.action == "buy" and not position.is_open:
            order_id = self._client_order_id("buy", latest)
            if order_id not in self.seen_client_order_ids:
                response = self.trading_client.submit_market_order(
                    symbol=self.run.symbol,
                    qty=float(decision.size or 0.0),
                    side="buy",
                    client_order_id=order_id,
                )
                if response.status in {"rejected", "canceled", "expired"}:
                    events.append(
                        ExecutionEvent(
                            event_type="order_rejected",
                            timestamp=latest.iso_timestamp,
                            status=response.status,
                            is_buy=True,
                            size=float(decision.size or 0.0),
                            price=latest.close,
                            value=float((decision.size or 0.0) * latest.close),
                            reason=decision.reason,
                            order_id=response.client_order_id,
                        )
                    )
                else:
                    self.seen_client_order_ids.add(order_id)
        elif decision.action in {"close", "trim"} and position.is_open:
            order_action = "trim" if decision.action == "trim" else "close"
            order_id = self._client_order_id(order_action, latest)
            if order_id not in self.seen_client_order_ids:
                sell_qty = float(abs(position.size))
                if decision.action == "trim":
                    sell_qty *= float(decision.portion or 0.0)
                response = self.trading_client.submit_market_order(
                    symbol=self.run.symbol,
                    qty=sell_qty,
                    side="sell",
                    client_order_id=order_id,
                )
                if response.status in {"rejected", "canceled", "expired"}:
                    events.append(
                        ExecutionEvent(
                            event_type="order_rejected",
                            timestamp=latest.iso_timestamp,
                            status=response.status,
                            is_buy=False,
                            size=sell_qty,
                            price=latest.close,
                            value=float(sell_qty * latest.close),
                            reason=decision.reason,
                            order_id=response.client_order_id,
                        )
                    )
                else:
                    self.seen_client_order_ids.add(order_id)

        next_position = position
        if position.is_open:
            next_position = PositionState(
                is_open=True,
                size=position.size,
                entry_price=position.entry_price,
                entry_bar_index=position.entry_bar_index,
                entry_time=position.entry_time,
                bars_held=position.bars_held,
            )
        self.snapshot = StrategyRuntimeSnapshot(
            last_processed_bar_time=latest.iso_timestamp,
            position=next_position,
            core_state=self.core.dump_state(),
        )
        self._save_snapshot()
        return events


def build_alpaca_executor(
    *,
    run: AlpacaTradingRunConfig,
    execution: AlpacaExecutionConfig,
    trading_client: AlpacaTradingClient | None = None,
    bar_source: AlpacaBarSource | None = None,
    state_store: RuntimeStateStore | None = None,
    include_candidate_log: bool | None = None,
) -> AlpacaStrategyExecutor:
    effective_execution = execution
    if include_candidate_log is not None:
        effective_execution = execution.model_copy(update={"include_candidate_log": include_candidate_log})
    return AlpacaStrategyExecutor(
        run=run,
        execution=effective_execution,
        trading_client=trading_client or HttpAlpacaTradingClient(effective_execution.mode),
        bar_source=bar_source or HttpAlpacaBarSource(),
        state_store=state_store or RuntimeStateStore(effective_execution.state_directory),
    )


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


def _interval_to_timedelta(interval: str) -> timedelta:
    mapping = {
        "1m": timedelta(minutes=1),
        "5m": timedelta(minutes=5),
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "1d": timedelta(days=1),
    }
    try:
        return mapping[interval]
    except KeyError as exc:
        raise RuntimeError(f"Unsupported interval '{interval}'") from exc
