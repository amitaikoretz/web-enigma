from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.live.assignments import AssignmentStore, heartbeat_from_runtime
from app.live.control_flags import ControlFlagStore
from app.live.controller import ContractsApiClient
from app.live.leases import LeaseStore
from app.live.models import (
    LeaseAcquireRequest,
    RuntimeContractState,
    TradingContractSnapshot,
    WorkerEventCreate,
    WorkerEventSeverity,
)
from app.live.persistence import WorkerEventRepository
from app.live.revocation import ContractRevocationStore, NoopContractRevocationStore


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
        contracts_api_client: ContractsApiClient | None = None,
        revocation_store: ContractRevocationStore | None = None,
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
        self.contracts_api_client = contracts_api_client
        self.revocation_store = revocation_store or NoopContractRevocationStore()
        self.worker_event_repository = worker_event_repository
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.lease_ttl_seconds = lease_ttl_seconds
        self.assignment_version = 0
        self.assigned_symbols: set[str] = set()
        self.owned_symbols: set[str] = set()
        self.owned_contracts: dict[UUID, TradingContractSnapshot] = {}
        self.is_draining = False

    def run_forever(self, max_iterations: int | None = None) -> None:
        self.register_heartbeat(RuntimeContractState.ASSIGNED)
        self._record_event("worker_started", WorkerEventSeverity.INFO, {"shard_id": self.shard_id})
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            self.refresh_assignments()
            self._release_unassigned_symbols()
            self._sync_active_contracts()
            self.acquire_and_warm_symbols()
            self.process_market_events()
            self.register_heartbeat(RuntimeContractState.TRADABLE if self.owned_symbols else RuntimeContractState.ASSIGNED)
            iterations += 1
            if max_iterations is None or iterations < max_iterations:
                time.sleep(self.heartbeat_interval_seconds)

    def refresh_assignments(self) -> None:
        previous_version = self.assignment_version
        self.assignment_version = self.assignment_store.get_assignment_version()
        self.assigned_symbols = self.assignment_store.get_shard_assignments(self.shard_id)
        if previous_version != self.assignment_version:
            self._record_event(
                "assignments_refreshed",
                WorkerEventSeverity.INFO,
                {
                    "assignment_version": self.assignment_version,
                    "assigned_symbols": sorted(self.assigned_symbols),
                },
            )

    def _release_unassigned_symbols(self) -> None:
        for symbol_key in sorted(self.owned_symbols - self.assigned_symbols):
            self.lease_store.release_symbol_lease(symbol_key, self.worker_id)
            self.owned_symbols.discard(symbol_key)
            revoked_contract_ids = [
                str(contract_id)
                for contract_id, contract in list(self.owned_contracts.items())
                if contract.symbol_key == symbol_key
            ]
            for contract_id in list(self.owned_contracts):
                if self.owned_contracts[contract_id].symbol_key == symbol_key:
                    self.owned_contracts.pop(contract_id, None)
            self._record_event(
                "symbol_released",
                WorkerEventSeverity.INFO,
                {"symbol_key": symbol_key, "reason": "symbol_no_longer_assigned"},
            )
            if revoked_contract_ids:
                self._record_event(
                    "assignments_shrunk",
                    WorkerEventSeverity.INFO,
                    {"symbol_key": symbol_key, "contract_ids": revoked_contract_ids},
                )

    def _sync_active_contracts(self) -> None:
        if self.contracts_api_client is None:
            return

        active_contracts = self.contracts_api_client.get_active_contracts(active_at=datetime.now(UTC))
        active_for_shard = [
            contract
            for contract in active_contracts
            if contract.symbol_key in self.assigned_symbols
        ]
        next_owned: dict[UUID, TradingContractSnapshot] = {}
        for contract in active_for_shard:
            if self.revocation_store.is_contract_revoked(contract.contract_id):
                if contract.contract_id in self.owned_contracts:
                    self._record_event(
                        "contract_revoked",
                        WorkerEventSeverity.WARNING,
                        {
                            "contract_id": str(contract.contract_id),
                            "symbol_key": contract.symbol_key,
                        },
                    )
                continue
            if self.control_flag_store.is_contract_paused(str(contract.contract_id)):
                continue
            next_owned[contract.contract_id] = contract

        dropped_contract_ids = set(self.owned_contracts) - set(next_owned)
        for contract_id in dropped_contract_ids:
            contract = self.owned_contracts[contract_id]
            self._record_event(
                "contract_revoked",
                WorkerEventSeverity.INFO,
                {
                    "contract_id": str(contract_id),
                    "symbol_key": contract.symbol_key,
                    "reason": "no_longer_active",
                },
            )
        self.owned_contracts = next_owned

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
            {
                "owned_symbols": sorted(self.owned_symbols),
                "owned_contract_ids": sorted(str(contract_id) for contract_id in self.owned_contracts),
                "draining": self.is_draining,
            },
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
        self.owned_contracts.clear()
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
        contract_id_raw = payload.get("contract_id")
        contract_id = UUID(str(contract_id_raw)) if isinstance(contract_id_raw, str) else None
        self.worker_event_repository.record(
            WorkerEventCreate(
                worker_id=self.worker_id,
                shard_id=self.shard_id,
                contract_id=contract_id,
                symbol_key=payload.get("symbol_key") if isinstance(payload.get("symbol_key"), str) else None,
                event_type=event_type,
                severity=severity,
                payload=payload,
            )
        )
