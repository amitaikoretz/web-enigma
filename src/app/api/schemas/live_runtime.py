from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class WorkerHeartbeatResponse(BaseModel):
    worker_id: str
    pod_name: str
    shard_id: int
    status: str
    owned_symbol_count: int
    updated_at: datetime


class ShardAssignmentResponse(BaseModel):
    shard_id: int
    symbol_keys: list[str]


class LeaseResponse(BaseModel):
    symbol_key: str
    worker_id: str
    pod_name: str
    shard_id: int
    assignment_version: int
    leased_at: datetime
    expires_at: datetime


class ControlFlagsResponse(BaseModel):
    kill_switch_enabled: bool
    paused_contracts: list[str]
    paused_symbols: list[str]
    paused_shards: list[int]


class RuntimeStateResponse(BaseModel):
    assignment_version: int
    assignments: list[ShardAssignmentResponse]
    workers: list[WorkerHeartbeatResponse]
    leases: list[LeaseResponse]
    control_flags: ControlFlagsResponse


class WorkerEventResponse(BaseModel):
    id: UUID
    worker_id: str
    shard_id: int | None
    contract_id: UUID | None
    symbol_key: str | None
    event_type: str
    severity: str
    payload: dict[str, Any]
    created_at: datetime


class LiveRuntimeResponse(BaseModel):
    state: RuntimeStateResponse
    events: list[WorkerEventResponse]


class LiveRuntimeEventsQuery(BaseModel):
    limit: int = Field(default=100, ge=1, le=500)
    worker_id: str | None = None
    event_type: str | None = None
    symbol_key: str | None = None
    since: datetime | None = None
    until: datetime | None = None
