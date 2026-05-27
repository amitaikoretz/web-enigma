from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func
from sqlalchemy import Uuid as SqlUuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db.base import Base


json_type = JSONB().with_variant(JSON(), "sqlite")


class TradingContract(Base):
    __tablename__ = "trading_contracts"
    __table_args__ = (
        Index("ix_trading_contracts_symbol_strategy", "symbol", "strategy"),
        Index("ix_trading_contracts_start_datetime", "start_datetime"),
        Index("ix_trading_contracts_end_datetime", "end_datetime"),
    )

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    strategy: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_params: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    start_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    maximum_trade_size: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    total_invested: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TradeIntent(Base):
    __tablename__ = "trade_intents"
    __table_args__ = (
        Index("ix_trade_intents_contract_created_at", "contract_id", "created_at"),
        Index("ix_trade_intents_symbol_key_created_at", "symbol_key", "created_at"),
        Index("ix_trade_intents_worker_created_at", "worker_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID] = mapped_column(SqlUuid, ForeignKey("trading_contracts.id"), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_key: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    shard_id: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    signal_payload: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    intended_side: Mapped[str] = mapped_column(String(16), nullable=False)
    intended_qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    intended_notional: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    run_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="paper_live")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BrokerOrder(Base):
    __tablename__ = "broker_orders"
    __table_args__ = (
        Index("ux_broker_orders_broker_client_order_id", "broker_name", "client_order_id", unique=True),
        Index("ux_broker_orders_broker_order_id", "broker_name", "broker_order_id", unique=True),
        Index("ix_broker_orders_symbol_key_status_submitted_at", "symbol_key", "status", "submitted_at"),
        Index("ix_broker_orders_contract_submitted_at", "contract_id", "submitted_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid.uuid4)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(SqlUuid, ForeignKey("trading_contracts.id"), nullable=True)
    trade_intent_id: Mapped[uuid.UUID | None] = mapped_column(SqlUuid, ForeignKey("trade_intents.id"), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_key: Mapped[str] = mapped_column(String(128), nullable=False)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    shard_id: Mapped[int] = mapped_column(Integer, nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    filled_qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    remaining_qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False)
    time_in_force: Mapped[str] = mapped_column(String(16), nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    stop_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    submission_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_broker_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    broker_response: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    run_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="paper_live")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_fill_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BrokerFill(Base):
    __tablename__ = "broker_fills"
    __table_args__ = (
        Index("ix_broker_fills_broker_order_fill_timestamp", "broker_order_id", "fill_timestamp"),
        Index("ix_broker_fills_symbol_key_fill_timestamp", "symbol_key", "fill_timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid.uuid4)
    broker_order_row_id: Mapped[uuid.UUID | None] = mapped_column(SqlUuid, ForeignKey("broker_orders.id"), nullable=True)
    broker_order_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_key: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    fill_qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    fill_price: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    fill_notional: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    run_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="paper_live")
    fill_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index("ux_positions_broker_symbol_key", "broker_name", "symbol_key", unique=True),
        Index("ix_positions_status_updated_at", "status", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid.uuid4)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol_key: Mapped[str] = mapped_column(String(128), nullable=False)
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    net_qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False, default=0)
    avg_entry_price: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    market_value: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_basis: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    realized_pnl: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    unrealized_pnl: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)
    last_fill_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_details: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    run_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="paper_live")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class PositionContractAllocation(Base):
    __tablename__ = "position_contract_allocations"
    __table_args__ = (
        Index("ix_position_contract_allocations_position_contract", "position_id", "contract_id"),
        Index("ix_position_contract_allocations_contract_updated_at", "contract_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid.uuid4)
    position_id: Mapped[uuid.UUID] = mapped_column(SqlUuid, ForeignKey("positions.id"), nullable=False)
    contract_id: Mapped[uuid.UUID] = mapped_column(SqlUuid, ForeignKey("trading_contracts.id"), nullable=False)
    allocated_qty: Mapped[float] = mapped_column(Numeric(18, 8), nullable=False)
    allocation_method: Mapped[str] = mapped_column(String(32), nullable=False)
    allocation_metadata: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReconciliationRun(Base):
    __tablename__ = "reconciliation_runs"
    __table_args__ = (
        Index("ix_reconciliation_runs_scope_started_at", "scope_type", "scope_id", "started_at"),
        Index("ix_reconciliation_runs_status_started_at", "status", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid.uuid4)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[str] = mapped_column(String(128), nullable=False)
    broker_name: Mapped[str] = mapped_column(String(32), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    mismatch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    summary: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BacktestJob(Base):
    __tablename__ = "backtest_jobs"
    __table_args__ = (
        Index("ix_backtest_jobs_status_updated_at", "status", "updated_at"),
        Index("ix_backtest_jobs_created_at", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    report_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    successful_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    failed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    selection: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_backend: Mapped[str] = mapped_column(String(16), nullable=False, default="local", server_default="local")
    workflow_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    workflow_namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_json_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidates_json_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    candidates_parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    equity_parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    orders_parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    trades_parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejections_parquet_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_path: Mapped[str | None] = mapped_column(Text, nullable=True)


class WorkerEvent(Base):
    __tablename__ = "worker_events"
    __table_args__ = (
        Index("ix_worker_events_worker_created_at", "worker_id", "created_at"),
        Index("ix_worker_events_event_type_created_at", "event_type", "created_at"),
        Index("ix_worker_events_symbol_key_created_at", "symbol_key", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(SqlUuid, primary_key=True, default=uuid.uuid4)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    shard_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(SqlUuid, ForeignKey("trading_contracts.id"), nullable=True)
    symbol_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
