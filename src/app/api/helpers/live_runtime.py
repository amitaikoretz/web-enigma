from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas.live_runtime import (
    ControlFlagsResponse,
    LeaseResponse,
    LiveRuntimeEventsQuery,
    RuntimeStateResponse,
    ShardAssignmentResponse,
    WorkerEventResponse,
    WorkerHeartbeatResponse,
)
from app.db.models import WorkerEvent
from app.live.assignments import RedisAssignmentStore
from app.live.control_flags import RedisControlFlagStore
from app.live.leases import RedisLeaseStore
from app.live.persistence import WorkerEventQuery


def build_runtime_state(
    *,
    assignment_store: RedisAssignmentStore,
    lease_store: RedisLeaseStore,
    control_flag_store: RedisControlFlagStore,
) -> RuntimeStateResponse:
    shard_assignments = assignment_store.list_shard_assignments()
    assignments = [
        ShardAssignmentResponse(shard_id=shard_id, symbol_keys=sorted(symbol_keys))
        for shard_id, symbol_keys in sorted(shard_assignments.items())
    ]
    workers = [
        WorkerHeartbeatResponse(
            worker_id=heartbeat.worker_id,
            pod_name=heartbeat.pod_name,
            shard_id=heartbeat.shard_id,
            status=heartbeat.status.value,
            owned_symbol_count=heartbeat.owned_symbol_count,
            updated_at=heartbeat.updated_at,
        )
        for heartbeat in sorted(assignment_store.list_worker_heartbeats(), key=lambda item: item.worker_id)
    ]
    leases = [
        LeaseResponse(
            symbol_key=lease.symbol_key,
            worker_id=lease.worker_id,
            pod_name=lease.pod_name,
            shard_id=lease.shard_id,
            assignment_version=lease.assignment_version,
            leased_at=lease.leased_at,
            expires_at=lease.expires_at,
        )
        for lease in sorted(lease_store.list_active_leases(), key=lambda item: item.symbol_key)
    ]
    control_flags_snapshot = control_flag_store.snapshot()
    control_flags = ControlFlagsResponse(
        kill_switch_enabled=control_flags_snapshot.kill_switch_enabled,
        paused_contracts=control_flags_snapshot.paused_contracts,
        paused_symbols=control_flags_snapshot.paused_symbols,
        paused_shards=control_flags_snapshot.paused_shards,
    )
    return RuntimeStateResponse(
        assignment_version=assignment_store.get_assignment_version(),
        assignments=assignments,
        workers=workers,
        leases=leases,
        control_flags=control_flags,
    )


def list_runtime_events(session: Session, query: LiveRuntimeEventsQuery) -> list[WorkerEventResponse]:
    worker_query = WorkerEventQuery(
        limit=query.limit,
        worker_id=query.worker_id,
        event_type=query.event_type,
        symbol_key=query.symbol_key,
        since=query.since,
        until=query.until,
    )
    stmt = select(WorkerEvent).order_by(WorkerEvent.created_at.desc()).limit(worker_query.limit)
    if worker_query.worker_id is not None:
        stmt = stmt.where(WorkerEvent.worker_id == worker_query.worker_id)
    if worker_query.event_type is not None:
        stmt = stmt.where(WorkerEvent.event_type == worker_query.event_type)
    if worker_query.symbol_key is not None:
        stmt = stmt.where(WorkerEvent.symbol_key == worker_query.symbol_key)
    if worker_query.since is not None:
        stmt = stmt.where(WorkerEvent.created_at >= worker_query.since)
    if worker_query.until is not None:
        stmt = stmt.where(WorkerEvent.created_at < worker_query.until)
    events = session.execute(stmt).scalars().all()
    return [_worker_event_to_response(event) for event in events]


def _worker_event_to_response(event: WorkerEvent) -> WorkerEventResponse:
    return WorkerEventResponse(
        id=event.id,
        worker_id=event.worker_id,
        shard_id=event.shard_id,
        contract_id=event.contract_id,
        symbol_key=event.symbol_key,
        event_type=event.event_type,
        severity=event.severity,
        payload=event.payload,
        created_at=event.created_at,
    )
