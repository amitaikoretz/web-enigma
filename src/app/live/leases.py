from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol

from app.live.assignments import RedisBackend
from app.live.models import LeaseAcquireRequest, LeaseAcquireResult, LeaseRecord, LeaseRenewRequest, LeaseRenewResult


class LeaseStore(Protocol):
    def acquire_symbol_lease(self, request: LeaseAcquireRequest) -> LeaseAcquireResult: ...

    def renew_symbol_lease(self, request: LeaseRenewRequest) -> LeaseRenewResult: ...

    def release_symbol_lease(self, symbol_key: str, worker_id: str) -> None: ...

    def get_symbol_lease(self, symbol_key: str) -> LeaseRecord | None: ...


class RedisLeaseStore:
    def __init__(self, *, backend: RedisBackend, key_prefix: str = "ta") -> None:
        self.backend = backend
        self.key_prefix = key_prefix

    def acquire_symbol_lease(self, request: LeaseAcquireRequest) -> LeaseAcquireResult:
        key = self._lease_key(request.symbol_key)
        existing = self.get_symbol_lease(request.symbol_key)
        if existing is not None and existing.expires_at > request.leased_at:
            return LeaseAcquireResult(acquired=False, lease=existing, reason="lease already held")
        lease = LeaseRecord(
            worker_id=request.worker_id,
            pod_name=request.pod_name,
            shard_id=request.shard_id,
            symbol_key=request.symbol_key,
            assignment_version=request.assignment_version,
            leased_at=request.leased_at,
            expires_at=request.expires_at,
        )
        self.backend.set(key, json.dumps(_lease_to_payload(lease)))
        return LeaseAcquireResult(acquired=True, lease=lease)

    def renew_symbol_lease(self, request: LeaseRenewRequest) -> LeaseRenewResult:
        current = self.get_symbol_lease(request.symbol_key)
        if current is None:
            return LeaseRenewResult(renewed=False, reason="lease missing")
        if current.worker_id != request.worker_id:
            return LeaseRenewResult(renewed=False, lease=current, reason="lease owned by another worker")
        lease = LeaseRecord(
            worker_id=current.worker_id,
            pod_name=current.pod_name,
            shard_id=current.shard_id,
            symbol_key=current.symbol_key,
            assignment_version=request.assignment_version,
            leased_at=request.leased_at,
            expires_at=request.expires_at,
        )
        self.backend.set(self._lease_key(request.symbol_key), json.dumps(_lease_to_payload(lease)))
        return LeaseRenewResult(renewed=True, lease=lease)

    def release_symbol_lease(self, symbol_key: str, worker_id: str) -> None:
        current = self.get_symbol_lease(symbol_key)
        if current is None or current.worker_id != worker_id:
            return
        self.backend.delete(self._lease_key(symbol_key))

    def get_symbol_lease(self, symbol_key: str) -> LeaseRecord | None:
        raw = self.backend.get(self._lease_key(symbol_key))
        if raw is None:
            return None
        payload = json.loads(raw)
        return LeaseRecord(
            worker_id=payload["worker_id"],
            pod_name=payload["pod_name"],
            shard_id=int(payload["shard_id"]),
            symbol_key=payload["symbol_key"],
            assignment_version=int(payload["assignment_version"]),
            leased_at=datetime.fromisoformat(payload["leased_at"]),
            expires_at=datetime.fromisoformat(payload["expires_at"]),
        )

    def list_active_leases(self, *, active_at: datetime | None = None) -> list[LeaseRecord]:
        now = active_at or datetime.now(UTC)
        prefix = f"{self.key_prefix}:lease:symbol:"
        leases: list[LeaseRecord] = []
        for key in self.backend.scan_keys(f"{prefix}*"):
            lease = self.get_symbol_lease(key.removeprefix(prefix))
            if lease is not None and lease.expires_at > now:
                leases.append(lease)
        return leases

    def _lease_key(self, symbol_key: str) -> str:
        return f"{self.key_prefix}:lease:symbol:{symbol_key}"


def _lease_to_payload(lease: LeaseRecord) -> dict[str, str | int]:
    return {
        "worker_id": lease.worker_id,
        "pod_name": lease.pod_name,
        "shard_id": lease.shard_id,
        "symbol_key": lease.symbol_key,
        "assignment_version": lease.assignment_version,
        "leased_at": lease.leased_at.isoformat(),
        "expires_at": lease.expires_at.isoformat(),
    }
