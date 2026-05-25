from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from app.db.models import (
    BrokerFill,
    BrokerOrder,
    Position,
    ReconciliationRun,
    TradeIntent,
    WorkerEvent,
)
from app.live.models import (
    BrokerFillCreate,
    BrokerOrderCreate,
    BrokerOrderStatus,
    BrokerOrderStatusUpdate,
    PositionStatus,
    PositionUpsert,
    ReconciliationResult,
    ReconciliationRunCreate,
    RuntimeContractState,
    TradeIntentCreate,
    WorkerEventCreate,
)


class TradeIntentRepository(Protocol):
    def create(self, intent: TradeIntentCreate) -> TradeIntent: ...

    def mark_submitted(self, intent_id: UUID, order_id: UUID) -> None: ...

    def mark_blocked(self, intent_id: UUID, reason: str) -> None: ...


class BrokerOrderRepository(Protocol):
    def create(self, order: BrokerOrderCreate) -> BrokerOrder: ...

    def get_by_client_order_id(self, broker_name: str, client_order_id: str) -> BrokerOrder | None: ...

    def update_status(self, order_id: UUID, update: BrokerOrderStatusUpdate) -> BrokerOrder | None: ...

    def list_open_by_symbol(self, symbol_key: str) -> list[BrokerOrder]: ...


class BrokerFillRepository(Protocol):
    def record_fill(self, fill: BrokerFillCreate) -> BrokerFill: ...

    def list_for_order(self, broker_order_id: str) -> list[BrokerFill]: ...


class PositionRepository(Protocol):
    def get_by_symbol(self, broker_name: str, symbol_key: str) -> Position | None: ...

    def upsert(self, position: PositionUpsert) -> Position: ...

    def list_open_positions(self) -> list[Position]: ...


class ReconciliationRepository(Protocol):
    def start_run(self, request: ReconciliationRunCreate) -> ReconciliationRun: ...

    def complete_run(self, run_id: UUID, result: ReconciliationResult) -> None: ...


class WorkerEventRepository(Protocol):
    def record(self, event: WorkerEventCreate) -> None: ...


class SqlAlchemyTradeIntentRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def create(self, intent: TradeIntentCreate) -> TradeIntent:
        with self.session_factory() as session:
            record = TradeIntent(
                contract_id=intent.contract_id,
                symbol=intent.symbol,
                symbol_key=intent.symbol_key,
                worker_id=intent.worker_id,
                shard_id=intent.shard_id,
                strategy_name=intent.strategy_name,
                signal_type=intent.signal_type,
                signal_hash=intent.signal_hash,
                signal_payload=intent.signal_payload,
                intended_side=intent.intended_side,
                intended_qty=Decimal(str(intent.intended_qty)),
                intended_notional=Decimal(str(intent.intended_notional)) if intent.intended_notional is not None else None,
                status=intent.status.value,
                decision_reason=intent.decision_reason,
                run_mode=intent.run_mode,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def mark_submitted(self, intent_id: UUID, order_id: UUID) -> None:
        raise NotImplementedError("Trade intent transitions are not implemented in this runtime skeleton")

    def mark_blocked(self, intent_id: UUID, reason: str) -> None:
        raise NotImplementedError("Trade intent transitions are not implemented in this runtime skeleton")


class SqlAlchemyBrokerOrderRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def create(self, order: BrokerOrderCreate) -> BrokerOrder:
        with self.session_factory() as session:
            record = BrokerOrder(
                contract_id=order.contract_id,
                trade_intent_id=order.trade_intent_id,
                symbol=order.symbol,
                symbol_key=order.symbol_key,
                worker_id=order.worker_id,
                shard_id=order.shard_id,
                client_order_id=order.client_order_id,
                broker_order_id=order.broker_order_id,
                broker_name=order.broker_name,
                side=order.side,
                qty=Decimal(str(order.qty)),
                order_type=order.order_type,
                time_in_force=order.time_in_force,
                status=order.status.value,
                run_mode=order.run_mode,
                submitted_at=order.submitted_at,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_by_client_order_id(self, broker_name: str, client_order_id: str) -> BrokerOrder | None:
        with self.session_factory() as session:
            return (
                session.query(BrokerOrder)
                .filter(BrokerOrder.broker_name == broker_name, BrokerOrder.client_order_id == client_order_id)
                .one_or_none()
            )

    def update_status(self, order_id: UUID, update: BrokerOrderStatusUpdate) -> BrokerOrder | None:
        raise NotImplementedError("Broker order status updates are not implemented in this runtime skeleton")

    def list_open_by_symbol(self, symbol_key: str) -> list[BrokerOrder]:
        with self.session_factory() as session:
            open_statuses = {
                BrokerOrderStatus.SUBMIT_PENDING.value,
                BrokerOrderStatus.SUBMITTED.value,
                BrokerOrderStatus.ACKNOWLEDGED.value,
                BrokerOrderStatus.PARTIALLY_FILLED.value,
            }
            return session.query(BrokerOrder).filter(BrokerOrder.symbol_key == symbol_key, BrokerOrder.status.in_(open_statuses)).all()


class SqlAlchemyBrokerFillRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def record_fill(self, fill: BrokerFillCreate) -> BrokerFill:
        with self.session_factory() as session:
            record = BrokerFill(
                broker_order_id=fill.broker_order_id,
                client_order_id=fill.client_order_id,
                symbol=fill.symbol,
                symbol_key=fill.symbol_key,
                side=fill.side,
                fill_qty=Decimal(str(fill.fill_qty)),
                fill_price=Decimal(str(fill.fill_price)),
                fill_notional=Decimal(str(fill.fill_notional)) if fill.fill_notional is not None else None,
                raw_payload=fill.raw_payload,
                run_mode=fill.run_mode,
                fill_timestamp=fill.fill_timestamp,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def list_for_order(self, broker_order_id: str) -> list[BrokerFill]:
        with self.session_factory() as session:
            return session.query(BrokerFill).filter(BrokerFill.broker_order_id == broker_order_id).all()


class SqlAlchemyPositionRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def get_by_symbol(self, broker_name: str, symbol_key: str) -> Position | None:
        with self.session_factory() as session:
            return (
                session.query(Position)
                .filter(Position.broker_name == broker_name, Position.symbol_key == symbol_key)
                .one_or_none()
            )

    def upsert(self, position: PositionUpsert) -> Position:
        raise NotImplementedError("Position upsert is not implemented in this runtime skeleton")

    def list_open_positions(self) -> list[Position]:
        with self.session_factory() as session:
            open_statuses = {PositionStatus.OPEN.value, PositionStatus.CLOSING.value, PositionStatus.RECONCILIATION_NEEDED.value}
            return session.query(Position).filter(Position.status.in_(open_statuses)).all()


class SqlAlchemyReconciliationRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def start_run(self, request: ReconciliationRunCreate) -> ReconciliationRun:
        with self.session_factory() as session:
            record = ReconciliationRun(
                worker_id=request.worker_id,
                scope_type=request.scope_type,
                scope_id=request.scope_id,
                broker_name=request.broker_name,
                mode=request.mode,
                status=request.status.value,
                mismatch_count=request.mismatch_count,
                summary=request.summary,
                started_at=request.started_at,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def complete_run(self, run_id: UUID, result: ReconciliationResult) -> None:
        raise NotImplementedError("Reconciliation completion is not implemented in this runtime skeleton")


class SqlAlchemyWorkerEventRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def record(self, event: WorkerEventCreate) -> None:
        with self.session_factory() as session:
            record = WorkerEvent(
                worker_id=event.worker_id,
                shard_id=event.shard_id,
                contract_id=event.contract_id,
                symbol_key=event.symbol_key,
                event_type=event.event_type,
                severity=event.severity.value,
                payload=event.payload,
            )
            session.add(record)
            session.commit()
