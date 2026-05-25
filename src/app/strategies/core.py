from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Sequence


DecisionAction = Literal["hold", "buy", "close"]
ExecutionEventType = Literal["order_filled", "trade_closed", "order_rejected"]


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_complete: bool = True

    @property
    def iso_timestamp(self) -> str:
        return self.timestamp.isoformat()


@dataclass(frozen=True)
class PositionState:
    is_open: bool = False
    size: float = 0.0
    entry_price: float | None = None
    entry_bar_index: int | None = None
    entry_time: str | None = None
    bars_held: int = 0


@dataclass(frozen=True)
class StrategyContext:
    bar: Bar
    bars: Sequence[Bar]
    position: PositionState
    symbol: str | None = None
    equity: float | None = None


@dataclass(frozen=True)
class StrategyDecision:
    action: DecisionAction = "hold"
    size: float | None = None
    reason: str | None = None

    @classmethod
    def hold(cls, reason: str | None = None) -> "StrategyDecision":
        return cls(action="hold", reason=reason)

    @classmethod
    def buy(cls, size: float, reason: str | None = None) -> "StrategyDecision":
        return cls(action="buy", size=float(size), reason=reason)

    @classmethod
    def close(cls, reason: str | None = None) -> "StrategyDecision":
        return cls(action="close", reason=reason)


@dataclass(frozen=True)
class ExecutionEvent:
    event_type: ExecutionEventType
    timestamp: str | None
    status: str
    is_buy: bool
    size: float
    price: float
    value: float
    commission: float = 0.0
    pnl: float | None = None
    pnlcomm: float | None = None
    reason: str | None = None
    order_id: str | None = None


@dataclass(frozen=True)
class StrategyDefinition:
    name: str
    description: str
    params_model: type[Any]
    factory: "StrategyFactory"
    warmup_bars: "WarmupResolver"


StrategyFactory = Any
WarmupResolver = Any


class StrategyCore(ABC):
    def load_state(self, state: dict[str, Any] | None) -> None:
        return None

    def dump_state(self) -> dict[str, Any]:
        return {}

    @abstractmethod
    def on_bar(self, context: StrategyContext) -> StrategyDecision:
        raise NotImplementedError


@dataclass
class StrategyRuntimeSnapshot:
    last_processed_bar_time: str | None = None
    position: PositionState = field(default_factory=PositionState)
    core_state: dict[str, Any] = field(default_factory=dict)
