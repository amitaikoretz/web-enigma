from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.cli import main
from app.live.assignments import RedisAssignmentStore, get_shared_redis_backend
from app.live.control_flags import RedisControlFlagStore
from app.live.assignment_publisher import compute_shard_id
from app.live.controller import ContractsControllerService, NoopWorkerScaler
from app.live.revocation import RedisContractRevocationStore
from app.live.leases import RedisLeaseStore
from app.live.models import SessionPhase, TradingContractSnapshot, WorkerEventCreate
from app.live.persistence import (
    SqlAlchemyBrokerFillRepository,
    SqlAlchemyBrokerOrderRepository,
    SqlAlchemyPositionRepository,
    SqlAlchemyReconciliationRepository,
    SqlAlchemyTradeIntentRepository,
    SqlAlchemyWorkerEventRepository,
)
from app.live.session import FixedSessionCalendar
from app.live.worker import WorkerRuntimeCoordinator


class FakeContractsApiClient:
    def __init__(self, contracts: list[TradingContractSnapshot]) -> None:
        self.contracts = contracts

    def get_active_contracts(self, active_at: datetime | None = None) -> list[TradingContractSnapshot]:
        return list(self.contracts)


class RecordingWorkerEventRepository:
    def __init__(self) -> None:
        self.events: list[WorkerEventCreate] = []

    def record(self, event: WorkerEventCreate) -> None:
        self.events.append(event)

    def list_events(self, query) -> list:
        return []


def _sample_contract(contract_id: str, symbol: str, strategy: str = "buy_and_hold") -> TradingContractSnapshot:
    return TradingContractSnapshot(
        contract_id=UUID(contract_id),
        symbol=symbol,
        strategy=strategy,
        strategy_params={"stake": 1},
        start_datetime=datetime.now(UTC) - timedelta(hours=1),
        end_datetime=datetime.now(UTC) + timedelta(hours=1),
        maximum_trade_size=1000.0,
        total_invested=2500.0,
    )


def test_live_runtime_repositories_and_stores_construct():
    engine = create_engine("sqlite:///:memory:", future=True)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    backend = get_shared_redis_backend("memory://test-construct")

    assert RedisAssignmentStore(backend=backend)
    assert RedisLeaseStore(backend=backend)
    assert RedisControlFlagStore(backend=backend)
    assert SqlAlchemyTradeIntentRepository(session_factory)
    assert SqlAlchemyBrokerOrderRepository(session_factory)
    assert SqlAlchemyBrokerFillRepository(session_factory)
    assert SqlAlchemyPositionRepository(session_factory)
    assert SqlAlchemyReconciliationRepository(session_factory)
    assert SqlAlchemyWorkerEventRepository(session_factory)


def test_controller_sync_groups_contracts_by_symbol_and_scales_open():
    backend = get_shared_redis_backend("memory://controller-open")
    assignment_store = RedisAssignmentStore(backend=backend)
    event_repo = RecordingWorkerEventRepository()
    contracts = [
        _sample_contract("aa0d74d7-7a8d-4fe4-a20f-b5d30e935001", "AAPL", "buy_and_hold"),
        _sample_contract("aa0d74d7-7a8d-4fe4-a20f-b5d30e935002", "AAPL", "sma_cross"),
        _sample_contract("aa0d74d7-7a8d-4fe4-a20f-b5d30e935003", "MSFT", "buy_and_hold"),
    ]
    service = ContractsControllerService(
        contracts_api_client=FakeContractsApiClient(contracts),
        assignment_store=assignment_store,
        session_calendar=FixedSessionCalendar(SessionPhase.OPEN),
        worker_scaler=NoopWorkerScaler(),
        shard_count=2,
        scale_up_replicas=2,
        poll_interval_seconds=1,
        worker_event_repository=event_repo,
    )

    result = service.sync_once()

    assert result.session_phase is SessionPhase.OPEN
    assert result.active_contract_count == 3
    assert result.active_symbol_count == 2
    assert result.desired_replicas == 2
    assigned_symbols = {symbol for symbols in result.assignments.values() for symbol in symbols}
    assert assigned_symbols == {"AAPL", "MSFT"}
    assert any(event.event_type == "controller_sync" for event in event_repo.events)


def test_controller_sync_scales_to_zero_when_closed():
    backend = get_shared_redis_backend("memory://controller-closed")
    assignment_store = RedisAssignmentStore(backend=backend)
    scaler = NoopWorkerScaler()
    service = ContractsControllerService(
        contracts_api_client=FakeContractsApiClient([_sample_contract("aa0d74d7-7a8d-4fe4-a20f-b5d30e935004", "NVDA")]),
        assignment_store=assignment_store,
        session_calendar=FixedSessionCalendar(SessionPhase.CLOSED),
        worker_scaler=scaler,
        shard_count=2,
        scale_up_replicas=2,
        poll_interval_seconds=1,
        worker_event_repository=None,
    )

    result = service.sync_once()

    assert result.desired_replicas == 0
    assert scaler.current_replicas() == 0


def test_worker_startup_registers_heartbeat_and_acquires_leases():
    backend = get_shared_redis_backend("memory://worker-startup")
    assignment_store = RedisAssignmentStore(backend=backend)
    lease_store = RedisLeaseStore(backend=backend)
    control_flags = RedisControlFlagStore(backend=backend)
    event_repo = RecordingWorkerEventRepository()
    shard_id = compute_shard_id("AAPL", 2)
    assignment_store.publish_assignments(1, {0: set(), 1: set()})
    assignment_store.publish_assignments(2, {0: {"AAPL"} if shard_id == 0 else set(), 1: {"AAPL"} if shard_id == 1 else set()})

    worker = WorkerRuntimeCoordinator(
        worker_id="worker-1",
        pod_name="pod-1",
        shard_id=shard_id,
        assignment_store=assignment_store,
        lease_store=lease_store,
        control_flag_store=control_flags,
        worker_event_repository=event_repo,
        heartbeat_interval_seconds=1,
        lease_ttl_seconds=20,
    )

    worker.run_forever(max_iterations=1)

    assert "AAPL" in worker.owned_symbols
    assert lease_store.get_symbol_lease("AAPL") is not None
    assert backend.get("ta:worker:worker-1:heartbeat") is not None
    assert any(event.event_type == "lease_acquired" for event in event_repo.events)


def test_worker_drain_releases_leases_and_clears_heartbeat():
    backend = get_shared_redis_backend("memory://worker-drain")
    assignment_store = RedisAssignmentStore(backend=backend)
    lease_store = RedisLeaseStore(backend=backend)
    control_flags = RedisControlFlagStore(backend=backend)
    event_repo = RecordingWorkerEventRepository()
    shard_id = compute_shard_id("MSFT", 2)
    assignment_store.publish_assignments(1, {0: set(), 1: set()})
    assignment_store.publish_assignments(2, {0: {"MSFT"} if shard_id == 0 else set(), 1: {"MSFT"} if shard_id == 1 else set()})

    worker = WorkerRuntimeCoordinator(
        worker_id="worker-2",
        pod_name="pod-2",
        shard_id=shard_id,
        assignment_store=assignment_store,
        lease_store=lease_store,
        control_flag_store=control_flags,
        worker_event_repository=event_repo,
        heartbeat_interval_seconds=1,
        lease_ttl_seconds=20,
    )
    worker.run_forever(max_iterations=1)

    worker.drain()

    assert worker.owned_symbols == set()
    assert lease_store.get_symbol_lease("MSFT") is None
    assert backend.get("ta:worker:worker-2:heartbeat") is None
    assert any(event.event_type == "worker_draining" for event in event_repo.events)


def test_worker_releases_lease_when_symbol_removed_from_assignments():
    backend = get_shared_redis_backend("memory://worker-release-unassigned")
    assignment_store = RedisAssignmentStore(backend=backend)
    lease_store = RedisLeaseStore(backend=backend)
    control_flags = RedisControlFlagStore(backend=backend)
    event_repo = RecordingWorkerEventRepository()
    shard_id = compute_shard_id("MSFT", 2)
    assignment_store.publish_assignments(1, {0: set(), 1: set()})
    assignment_store.publish_assignments(2, {0: {"MSFT"} if shard_id == 0 else set(), 1: {"MSFT"} if shard_id == 1 else set()})

    worker = WorkerRuntimeCoordinator(
        worker_id="worker-release",
        pod_name="pod-release",
        shard_id=shard_id,
        assignment_store=assignment_store,
        lease_store=lease_store,
        control_flag_store=control_flags,
        contracts_api_client=FakeContractsApiClient([_sample_contract("aa0d74d7-7a8d-4fe4-a20f-b5d30e935010", "MSFT")]),
        worker_event_repository=event_repo,
        heartbeat_interval_seconds=1,
        lease_ttl_seconds=20,
    )
    worker.run_forever(max_iterations=1)
    assert "MSFT" in worker.owned_symbols

    assignment_store.publish_assignments(3, {0: set(), 1: set()})
    worker.run_forever(max_iterations=1)

    assert worker.owned_symbols == set()
    assert lease_store.get_symbol_lease("MSFT") is None
    assert any(event.event_type == "symbol_released" for event in event_repo.events)


def test_worker_drops_revoked_contract_but_keeps_symbol_lease_for_remaining_contract():
    backend = get_shared_redis_backend("memory://worker-revoke-one")
    assignment_store = RedisAssignmentStore(backend=backend)
    lease_store = RedisLeaseStore(backend=backend)
    control_flags = RedisControlFlagStore(backend=backend)
    revocation_store = RedisContractRevocationStore(backend=backend)
    event_repo = RecordingWorkerEventRepository()
    shard_id = compute_shard_id("AAPL", 2)
    contract_a = _sample_contract("aa0d74d7-7a8d-4fe4-a20f-b5d30e935011", "AAPL", "buy_and_hold")
    contract_b = _sample_contract("aa0d74d7-7a8d-4fe4-a20f-b5d30e935012", "AAPL", "sma_cross")
    assignment_store.publish_assignments(
        1,
        {0: {"AAPL"} if shard_id == 0 else set(), 1: {"AAPL"} if shard_id == 1 else set()},
    )

    worker = WorkerRuntimeCoordinator(
        worker_id="worker-revoke",
        pod_name="pod-revoke",
        shard_id=shard_id,
        assignment_store=assignment_store,
        lease_store=lease_store,
        control_flag_store=control_flags,
        contracts_api_client=FakeContractsApiClient([contract_a, contract_b]),
        revocation_store=revocation_store,
        worker_event_repository=event_repo,
        heartbeat_interval_seconds=1,
        lease_ttl_seconds=20,
    )
    worker.run_forever(max_iterations=1)
    assert "AAPL" in worker.owned_symbols
    assert set(worker.owned_contracts) == {contract_a.contract_id, contract_b.contract_id}

    revocation_store.revoke_contract(contract_a.contract_id, revision=2)
    worker.run_forever(max_iterations=1)

    assert "AAPL" in worker.owned_symbols
    assert worker.owned_contracts == {contract_b.contract_id: contract_b}
    assert any(event.event_type == "contract_revoked" for event in event_repo.events)


def test_cli_live_controller_invokes_builder(monkeypatch, tmp_path: Path):
    called: dict[str, object] = {}

    class FakeController:
        def sync_once(self):
            called["sync_once"] = True

            class Result:
                session_phase = SessionPhase.OPEN
                assignment_version = 1
                active_symbol_count = 1
                desired_replicas = 2

            return Result()

        def run_forever(self):
            called["run_forever"] = True

    monkeypatch.setattr("app.cli.live_runtime.build_live_controller", lambda config: FakeController())
    cfg_path = tmp_path / "live.yaml"
    cfg_path.write_text(yaml.safe_dump({"contracts": []}), encoding="utf-8")

    code = main(["live-controller", "--config", str(cfg_path), "--once"])

    assert code == 0
    assert called["sync_once"] is True


def test_cli_live_worker_invokes_builder(monkeypatch, tmp_path: Path):
    called: dict[str, object] = {}

    class FakeWorker:
        def run_forever(self, max_iterations=None):
            called["iterations"] = max_iterations

        def drain(self):
            called["drain"] = True

    monkeypatch.setattr("app.cli.live_runtime.build_live_worker", lambda config, shard_id: FakeWorker())
    cfg_path = tmp_path / "live.yaml"
    cfg_path.write_text(yaml.safe_dump({"contracts": []}), encoding="utf-8")

    code = main(["live-worker", "--config", str(cfg_path), "--shard-id", "0", "--once"])

    assert code == 0
    assert called["iterations"] == 1
    assert called["drain"] is True


def test_cli_live_reconciler_invokes_builder(monkeypatch, tmp_path: Path):
    called: dict[str, object] = {}

    class FakeReconciler:
        def run_once(self):
            called["run_once"] = True

            class Result:
                status = type("Status", (), {"value": "succeeded"})

            return [Result()]

    monkeypatch.setattr("app.cli.live_runtime.build_live_reconciler", lambda config: FakeReconciler())
    cfg_path = tmp_path / "live.yaml"
    cfg_path.write_text(yaml.safe_dump({"contracts": []}), encoding="utf-8")

    code = main(["live-reconciler", "--config", str(cfg_path), "--once"])

    assert code == 0
    assert called["run_once"] is True
