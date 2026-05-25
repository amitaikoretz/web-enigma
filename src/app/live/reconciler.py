from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from app.live.broker import BrokerAdapter
from app.live.market_data import MarketDataAdapter
from app.live.models import ReconciliationResult, ReconciliationRunCreate, ReconciliationRunStatus, WorkerEventCreate, WorkerEventSeverity
from app.live.persistence import (
    BrokerFillRepository,
    BrokerOrderRepository,
    PositionRepository,
    ReconciliationRepository,
    TradeIntentRepository,
    WorkerEventRepository,
)


class ReconciliationService(Protocol):
    def reconcile_symbol(self, symbol_key: str) -> ReconciliationResult: ...

    def reconcile_worker_scope(self, worker_id: str) -> list[ReconciliationResult]: ...

    def run_once(self) -> list[ReconciliationResult]: ...


class PlaceholderReconciliationService:
    def __init__(
        self,
        *,
        reconciliation_repository: ReconciliationRepository,
        worker_event_repository: WorkerEventRepository | None,
        broker_adapter: BrokerAdapter,
        market_data_adapter: MarketDataAdapter,
        broker_order_repository: BrokerOrderRepository,
        broker_fill_repository: BrokerFillRepository,
        position_repository: PositionRepository,
        trade_intent_repository: TradeIntentRepository,
        run_mode: str,
    ) -> None:
        self.reconciliation_repository = reconciliation_repository
        self.worker_event_repository = worker_event_repository
        self.broker_adapter = broker_adapter
        self.market_data_adapter = market_data_adapter
        self.broker_order_repository = broker_order_repository
        self.broker_fill_repository = broker_fill_repository
        self.position_repository = position_repository
        self.trade_intent_repository = trade_intent_repository
        self.run_mode = run_mode

    def reconcile_symbol(self, symbol_key: str) -> ReconciliationResult:
        started_at = datetime.now(UTC)
        self.reconciliation_repository.start_run(
            ReconciliationRunCreate(
                worker_id=None,
                scope_type="symbol",
                scope_id=symbol_key,
                broker_name=self.broker_adapter.broker_name,
                mode=self.run_mode,
                started_at=started_at,
                status=ReconciliationRunStatus.RUNNING,
            )
        )
        result = ReconciliationResult(
            scope_type="symbol",
            scope_id=symbol_key,
            status=ReconciliationRunStatus.SUCCEEDED,
            mismatch_count=0,
            summary={"detail": "placeholder reconciliation"},
        )
        self._record_event("reconciliation_symbol", {"symbol_key": symbol_key, "status": result.status.value})
        return result

    def reconcile_worker_scope(self, worker_id: str) -> list[ReconciliationResult]:
        result = ReconciliationResult(
            scope_type="worker",
            scope_id=worker_id,
            status=ReconciliationRunStatus.SUCCEEDED,
            mismatch_count=0,
            summary={"detail": "placeholder worker-scope reconciliation"},
        )
        self._record_event("reconciliation_worker", {"worker_id": worker_id, "status": result.status.value})
        return [result]

    def run_once(self) -> list[ReconciliationResult]:
        result = ReconciliationResult(
            scope_type="global",
            scope_id="all",
            status=ReconciliationRunStatus.SUCCEEDED,
            mismatch_count=0,
            summary={"detail": "placeholder reconciliation run"},
        )
        self._record_event("reconciliation_run", {"scope": "all", "status": result.status.value})
        return [result]

    def _record_event(self, event_type: str, payload: dict[str, object]) -> None:
        if self.worker_event_repository is None:
            return
        self.worker_event_repository.record(
            WorkerEventCreate(
                worker_id="reconciler",
                shard_id=None,
                contract_id=None,
                symbol_key=payload.get("symbol_key") if isinstance(payload.get("symbol_key"), str) else None,
                event_type=event_type,
                severity=WorkerEventSeverity.INFO,
                payload=payload,
            )
        )
