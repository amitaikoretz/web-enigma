from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

from app.live.assignments import AssignmentStore, heartbeat_from_runtime
from app.live.control_flags import ControlFlagStore
from app.live.leases import LeaseStore
from app.live.models import (
    LeaseAcquireRequest,
    RuntimeContractState,
    WorkerEventCreate,
    WorkerEventSeverity,
)
from app.live.persistence import WorkerEventRepository


class WorkerRuntimeCoordinator:
    def __init__(
        self,
        *,
        worker_id: str,
        pod_name: str,
        shard_id: int,
        assignment_store: AssignmentStore,
        lease_store: LeaseStore,
        control_flag_store: ControlFlagStore,
        worker_event_repository: WorkerEventRepository | None,
        heartbeat_interval_seconds: int,
        lease_ttl_seconds: int,
    ) -> None:
        self.worker_id = worker_id
        self.pod_name = pod_name
        self.shard_id = shard_id
        self.assignment_store = assignment_store
        self.lease_store = lease_store
        self.control_flag_store = control_flag_store
        self.worker_event_repository = worker_event_repository
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.lease_ttl_seconds = lease_ttl_seconds
        self.assignment_version = 0
        self.assigned_symbols: set[str] = set()
        self.owned_symbols: set[str] = set()
        self.is_draining = False

    def run_forever(self, max_iterations: int | None = None) -> None:
        self.register_heartbeat(RuntimeContractState.ASSIGNED)
        self._record_event("worker_started", WorkerEventSeverity.INFO, {"shard_id": self.shard_id})
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            self.refresh_assignments()
            self.acquire_and_warm_symbols()
            self.process_market_events()
            self.register_heartbeat(RuntimeContractState.TRADABLE if self.owned_symbols else RuntimeContractState.ASSIGNED)
            iterations += 1
            if max_iterations is None or iterations < max_iterations:
                time.sleep(self.heartbeat_interval_seconds)

    def refresh_assignments(self) -> None:
        self.assignment_version = self.assignment_store.get_assignment_version()
        self.assigned_symbols = self.assignment_store.get_shard_assignments(self.shard_id)
        self._record_event(
            "assignments_refreshed",
            WorkerEventSeverity.INFO,
            {
                "assignment_version": self.assignment_version,
                "assigned_symbols": sorted(self.assigned_symbols),
            },
        )

    def acquire_and_warm_symbols(self) -> None:
        now = datetime.now(UTC)
        for symbol_key in sorted(self.assigned_symbols):
            if self.control_flag_store.is_global_kill_switch_enabled() or self.control_flag_store.is_symbol_paused(symbol_key):
                continue
            if symbol_key in self.owned_symbols:
                continue
            result = self.lease_store.acquire_symbol_lease(
                LeaseAcquireRequest(
                    worker_id=self.worker_id,
                    pod_name=self.pod_name,
                    shard_id=self.shard_id,
                    symbol_key=symbol_key,
                    assignment_version=self.assignment_version,
                    leased_at=now,
                    expires_at=now + timedelta(seconds=self.lease_ttl_seconds),
                )
            )
            if result.acquired:
                self.owned_symbols.add(symbol_key)
                self._record_event("lease_acquired", WorkerEventSeverity.INFO, {"symbol_key": symbol_key})
            else:
                self._record_event(
                    "lease_skipped",
                    WorkerEventSeverity.WARNING,
                    {"symbol_key": symbol_key, "reason": result.reason},
                )

    def process_market_events(self) -> None:
        self._record_event(
            "worker_iteration",
            WorkerEventSeverity.DEBUG,
            {"owned_symbols": sorted(self.owned_symbols), "draining": self.is_draining},
        )

    def drain(self) -> None:
        self.is_draining = True
        self.register_heartbeat(RuntimeContractState.DRAINING)
        self._record_event(
            "worker_draining",
            WorkerEventSeverity.INFO,
            {"owned_symbols": sorted(self.owned_symbols)},
        )
        for symbol_key in list(self.owned_symbols):
            self.lease_store.release_symbol_lease(symbol_key, self.worker_id)
            self.owned_symbols.discard(symbol_key)
        self.assignment_store.clear_worker_heartbeat(self.worker_id)

    def register_heartbeat(self, status: RuntimeContractState) -> None:
        self.assignment_store.set_worker_heartbeat(
            heartbeat_from_runtime(
                worker_id=self.worker_id,
                pod_name=self.pod_name,
                shard_id=self.shard_id,
                status=status,
                owned_symbol_count=len(self.owned_symbols),
                updated_at=datetime.now(UTC),
            )
        )

    def _record_event(self, event_type: str, severity: WorkerEventSeverity, payload: dict[str, object]) -> None:
        if self.worker_event_repository is None:
            return
        self.worker_event_repository.record(
            WorkerEventCreate(
                worker_id=self.worker_id,
                shard_id=self.shard_id,
                contract_id=None,
                symbol_key=payload.get("symbol_key") if isinstance(payload.get("symbol_key"), str) else None,
                event_type=event_type,
                severity=severity,
                payload=payload,
            )
        )
