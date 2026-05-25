from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID


class SessionPhase(StrEnum):
    CLOSED = "closed"
    PRE_OPEN = "pre_open"
    OPEN = "open"
    DRAINING = "draining"


class RuntimeContractState(StrEnum):
    DISCOVERED = "discovered"
    ASSIGNED = "assigned"
    LEASING = "leasing"
    WARMING = "warming"
    TRADABLE = "tradable"
    PAUSED = "paused"
    DRAINING = "draining"
    CLOSED = "closed"
    RECONCILIATION_NEEDED = "reconciliation_needed"


class TradeIntentStatus(StrEnum):
    CREATED = "created"
    BLOCKED = "blocked"
    SUBMIT_REQUESTED = "submit_requested"
    SUBMITTED = "submitted"
    REJECTED = "rejected"
    CANCELED = "canceled"
    RECONCILED = "reconciled"


class BrokerOrderStatus(StrEnum):
    SUBMIT_PENDING = "submit_pending"
    SUBMITTED = "submitted"
    ACKNOWLEDGED = "acknowledged"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCEL_PENDING = "cancel_pending"
    CANCELED = "canceled"
    REJECTED = "rejected"
    EXPIRED = "expired"
    UNKNOWN_BROKER_OUTCOME = "unknown_broker_outcome"
    RECONCILED = "reconciled"


class PositionStatus(StrEnum):
    FLAT = "flat"
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"
    RECONCILIATION_NEEDED = "reconciliation_needed"


class ReconciliationRunStatus(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    SUCCEEDED_WITH_REPAIRS = "succeeded_with_repairs"
    FAILED = "failed"


class WorkerEventSeverity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ExecutionContext:
    run_mode: str
    broker_name: str
    session_phase: SessionPhase
    assignment_version: int
    worker_id: str
    shard_id: int


@dataclass(frozen=True)
class SymbolAssignment:
    symbol_key: str
    shard_id: int
    assignment_version: int
    contract_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True)
class LeaseRecord:
    worker_id: str
    pod_name: str
    shard_id: int
    symbol_key: str
    assignment_version: int
    leased_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class WorkerHeartbeat:
    worker_id: str
    pod_name: str
    shard_id: int
    status: RuntimeContractState
    owned_symbol_count: int
    updated_at: datetime


@dataclass(frozen=True)
class ReconciliationResult:
    scope_type: str
    scope_id: str
    status: ReconciliationRunStatus
    mismatch_count: int = 0
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TradingContractSnapshot:
    contract_id: UUID
    symbol: str
    strategy: str
    strategy_params: dict[str, Any]
    start_datetime: datetime
    end_datetime: datetime
    maximum_trade_size: float
    total_invested: float

    @property
    def symbol_key(self) -> str:
        return self.symbol.upper()


@dataclass(frozen=True)
class ControllerSyncResult:
    session_phase: SessionPhase
    assignment_version: int
    active_contract_count: int
    active_symbol_count: int
    desired_replicas: int
    assignments: dict[int, tuple[str, ...]]


@dataclass(frozen=True)
class SubmitOrderRequest:
    symbol: str
    qty: float
    side: str
    client_order_id: str
    order_type: str = "market"
    time_in_force: str = "day"


@dataclass(frozen=True)
class BrokerOrderAck:
    broker_order_id: str
    client_order_id: str
    status: BrokerOrderStatus
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerOrderSnapshot:
    broker_order_id: str
    client_order_id: str
    symbol: str
    side: str
    qty: float
    filled_qty: float
    status: BrokerOrderStatus
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerPositionSnapshot:
    symbol: str
    qty: float
    avg_entry_price: float | None = None
    market_value: float | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerFillSnapshot:
    broker_order_id: str
    symbol: str
    side: str
    fill_qty: float
    fill_price: float
    fill_timestamp: datetime
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrokerHealthStatus:
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class MarketDataHealthStatus:
    ok: bool
    detail: str = ""


@dataclass(frozen=True)
class MarketEvent:
    symbol: str
    occurred_at: datetime
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LeaseAcquireRequest:
    worker_id: str
    pod_name: str
    shard_id: int
    symbol_key: str
    assignment_version: int
    leased_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class LeaseAcquireResult:
    acquired: bool
    lease: LeaseRecord | None = None
    reason: str | None = None


@dataclass(frozen=True)
class LeaseRenewRequest:
    worker_id: str
    symbol_key: str
    assignment_version: int
    leased_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class LeaseRenewResult:
    renewed: bool
    lease: LeaseRecord | None = None
    reason: str | None = None


@dataclass(frozen=True)
class TradeIntentCreate:
    contract_id: UUID
    symbol: str
    symbol_key: str
    worker_id: str
    shard_id: int
    strategy_name: str
    signal_type: str
    signal_hash: str
    signal_payload: dict[str, Any]
    intended_side: str
    intended_qty: float
    intended_notional: float | None
    status: TradeIntentStatus
    decision_reason: str | None
    run_mode: str


@dataclass(frozen=True)
class BrokerOrderCreate:
    contract_id: UUID | None
    trade_intent_id: UUID | None
    symbol: str
    symbol_key: str
    worker_id: str
    shard_id: int
    client_order_id: str
    broker_order_id: str | None
    broker_name: str
    side: str
    qty: float
    order_type: str
    time_in_force: str
    status: BrokerOrderStatus
    submitted_at: datetime
    run_mode: str


@dataclass(frozen=True)
class BrokerOrderStatusUpdate:
    status: BrokerOrderStatus
    filled_qty: float | None = None
    remaining_qty: float | None = None
    acknowledged_at: datetime | None = None
    last_fill_at: datetime | None = None
    closed_at: datetime | None = None
    last_broker_message: str | None = None
    broker_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class BrokerFillCreate:
    broker_order_id: str
    client_order_id: str | None
    symbol: str
    symbol_key: str
    side: str
    fill_qty: float
    fill_price: float
    fill_notional: float | None
    fill_timestamp: datetime
    raw_payload: dict[str, Any]
    run_mode: str


@dataclass(frozen=True)
class PositionUpsert:
    symbol: str
    symbol_key: str
    broker_name: str
    net_qty: float
    avg_entry_price: float | None
    market_value: float | None
    cost_basis: float | None
    realized_pnl: float | None
    unrealized_pnl: float | None
    last_fill_at: datetime | None
    last_reconciled_at: datetime | None
    status: PositionStatus
    source: str
    source_details: dict[str, Any]
    run_mode: str


@dataclass(frozen=True)
class ReconciliationRunCreate:
    worker_id: str | None
    scope_type: str
    scope_id: str
    broker_name: str
    mode: str
    started_at: datetime
    status: ReconciliationRunStatus
    mismatch_count: int = 0
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class WorkerEventCreate:
    worker_id: str
    shard_id: int | None
    contract_id: UUID | None
    symbol_key: str | None
    event_type: str
    severity: WorkerEventSeverity
    payload: dict[str, Any] = field(default_factory=dict)
