from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import UUID

from app.live.assignments import AssignmentStore
from app.live.models import ControllerSyncResult, SessionPhase, TradingContractSnapshot, WorkerEventCreate, WorkerEventSeverity
from app.live.persistence import WorkerEventRepository
from app.live.session import SessionCalendar


class ContractsApiClient(Protocol):
    def get_active_contracts(self, active_at: datetime | None = None) -> list[TradingContractSnapshot]: ...


class WorkerScaler(Protocol):
    def scale_to(self, replica_count: int) -> None: ...

    def current_replicas(self) -> int: ...


class NoopWorkerScaler:
    def __init__(self) -> None:
        self._replicas = 0

    def scale_to(self, replica_count: int) -> None:
        self._replicas = replica_count

    def current_replicas(self) -> int:
        return self._replicas


class HttpContractsApiClient:
    def __init__(self, *, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    def get_active_contracts(self, active_at: datetime | None = None) -> list[TradingContractSnapshot]:
        params = {}
        if active_at is not None:
            params["active_at"] = active_at.isoformat()
        url = f"{self.base_url}/trading-contracts/active"
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(url, headers={"accept": "application/json"})
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return [
            TradingContractSnapshot(
                contract_id=UUID(item["id"]),
                symbol=item["symbol"],
                strategy=item["strategy"],
                strategy_params=item.get("strategy_params", {}),
                start_datetime=datetime.fromisoformat(item["start_datetime"]),
                end_datetime=datetime.fromisoformat(item["end_datetime"]),
                maximum_trade_size=float(item["maximum_trade_size"]),
                total_invested=float(item["total_invested"]),
            )
            for item in payload
        ]


class ContractsControllerService:
    def __init__(
        self,
        *,
        contracts_api_client: ContractsApiClient,
        assignment_store: AssignmentStore,
        session_calendar: SessionCalendar,
        worker_scaler: WorkerScaler,
        shard_count: int,
        scale_up_replicas: int,
        poll_interval_seconds: int,
        worker_event_repository: WorkerEventRepository | None = None,
    ) -> None:
        self.contracts_api_client = contracts_api_client
        self.assignment_store = assignment_store
        self.session_calendar = session_calendar
        self.worker_scaler = worker_scaler
        self.shard_count = shard_count
        self.scale_up_replicas = scale_up_replicas
        self.poll_interval_seconds = poll_interval_seconds
        self.worker_event_repository = worker_event_repository

    def sync_once(self, active_at: datetime | None = None) -> ControllerSyncResult:
        now = active_at or datetime.now(UTC)
        phase = self.session_calendar.get_phase(now)
        contracts = self.contracts_api_client.get_active_contracts(active_at=now)
        grouped = _group_contracts_by_symbol(contracts)
        assignments = _compute_assignments(grouped.keys(), self.shard_count)
        current_version = self.assignment_store.get_assignment_version()
        next_version = current_version + 1
        self.assignment_store.publish_assignments(next_version, assignments)
        desired_replicas = 0 if phase is SessionPhase.CLOSED else self.scale_up_replicas
        self.worker_scaler.scale_to(desired_replicas)
        self._record_event(
            event_type="controller_sync",
            severity=WorkerEventSeverity.INFO,
            payload={
                "phase": phase.value,
                "assignment_version": next_version,
                "active_contract_count": len(contracts),
                "active_symbol_count": len(grouped),
                "desired_replicas": desired_replicas,
            },
        )
        return ControllerSyncResult(
            session_phase=phase,
            assignment_version=next_version,
            active_contract_count=len(contracts),
            active_symbol_count=len(grouped),
            desired_replicas=desired_replicas,
            assignments={shard_id: tuple(sorted(symbols)) for shard_id, symbols in assignments.items()},
        )

    def run_forever(self, max_iterations: int | None = None) -> None:
        iterations = 0
        while max_iterations is None or iterations < max_iterations:
            self.sync_once()
            iterations += 1
            if max_iterations is None or iterations < max_iterations:
                time.sleep(self.poll_interval_seconds)

    def _record_event(self, *, event_type: str, severity: WorkerEventSeverity, payload: dict[str, object]) -> None:
        if self.worker_event_repository is None:
            return
        self.worker_event_repository.record(
            WorkerEventCreate(
                worker_id="controller",
                shard_id=None,
                contract_id=None,
                symbol_key=None,
                event_type=event_type,
                severity=severity,
                payload=payload,
            )
        )


def _group_contracts_by_symbol(contracts: list[TradingContractSnapshot]) -> dict[str, list[TradingContractSnapshot]]:
    grouped: dict[str, list[TradingContractSnapshot]] = defaultdict(list)
    for contract in contracts:
        grouped[contract.symbol_key].append(contract)
    return grouped


def compute_shard_id(symbol_key: str, shard_count: int) -> int:
    digest = hashlib.sha256(symbol_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % shard_count


def _compute_assignments(symbol_keys: object, shard_count: int) -> dict[int, set[str]]:
    assignments = {shard_id: set() for shard_id in range(shard_count)}
    for symbol_key in sorted(symbol_keys):
        assignments[compute_shard_id(str(symbol_key), shard_count)].add(str(symbol_key))
    return assignments
