from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Protocol

from app.live.models import RuntimeContractState, WorkerHeartbeat


class RedisBackend(Protocol):
    def get(self, key: str) -> Any: ...

    def set(self, key: str, value: Any) -> None: ...

    def delete(self, key: str) -> None: ...

    def set_members(self, key: str, values: Iterable[str]) -> None: ...

    def get_members(self, key: str) -> set[str]: ...

    def scan_keys(self, pattern: str) -> list[str]: ...


class InMemoryRedisBackend:
    def __init__(self) -> None:
        self._values: dict[str, Any] = {}
        self._sets: dict[str, set[str]] = {}

    def get(self, key: str) -> Any:
        return self._values.get(key)

    def set(self, key: str, value: Any) -> None:
        self._values[key] = value

    def delete(self, key: str) -> None:
        self._values.pop(key, None)
        self._sets.pop(key, None)

    def set_members(self, key: str, values: Iterable[str]) -> None:
        self._sets[key] = set(values)

    def get_members(self, key: str) -> set[str]:
        return set(self._sets.get(key, set()))

    def scan_keys(self, pattern: str) -> list[str]:
        keys = set(self._values) | set(self._sets)
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return sorted(key for key in keys if key.startswith(prefix))
        return sorted(key for key in keys if key == pattern)


_BACKENDS_BY_URL: dict[str, RedisBackend] = {}


def get_shared_redis_backend(url: str) -> RedisBackend:
    backend = _BACKENDS_BY_URL.get(url)
    if backend is not None:
        return backend
    if url.startswith("memory://"):
        backend = InMemoryRedisBackend()
    else:
        from app.live.redis_backend import RedisClientBackend

        backend = RedisClientBackend(url)
    _BACKENDS_BY_URL[url] = backend
    return backend


class AssignmentStore(Protocol):
    def get_assignment_version(self) -> int: ...

    def publish_assignments(self, version: int, assignments: dict[int, set[str]]) -> None: ...

    def get_shard_assignments(self, shard_id: int) -> set[str]: ...

    def set_worker_heartbeat(self, heartbeat: WorkerHeartbeat) -> None: ...

    def clear_worker_heartbeat(self, worker_id: str) -> None: ...


class RedisAssignmentStore:
    def __init__(self, *, backend: RedisBackend, key_prefix: str = "ta") -> None:
        self.backend = backend
        self.key_prefix = key_prefix

    def get_assignment_version(self) -> int:
        raw = self.backend.get(self._assignment_version_key())
        if raw is None:
            return 0
        return int(raw)

    def publish_assignments(self, version: int, assignments: dict[int, set[str]]) -> None:
        self.backend.set(self._assignment_version_key(), str(version))
        for shard_id, symbols in assignments.items():
            self.backend.set_members(self._assignment_key(shard_id), sorted(symbols))

    def get_shard_assignments(self, shard_id: int) -> set[str]:
        return self.backend.get_members(self._assignment_key(shard_id))

    def set_worker_heartbeat(self, heartbeat: WorkerHeartbeat) -> None:
        payload = {
            "worker_id": heartbeat.worker_id,
            "pod_name": heartbeat.pod_name,
            "shard_id": heartbeat.shard_id,
            "status": heartbeat.status.value,
            "owned_symbol_count": heartbeat.owned_symbol_count,
            "updated_at": heartbeat.updated_at.isoformat(),
        }
        self.backend.set(self._heartbeat_key(heartbeat.worker_id), json.dumps(payload))

    def clear_worker_heartbeat(self, worker_id: str) -> None:
        self.backend.delete(self._heartbeat_key(worker_id))

    def list_shard_assignments(self) -> dict[int, set[str]]:
        prefix = f"{self.key_prefix}:assignments:shard:"
        assignments: dict[int, set[str]] = {}
        for key in self.backend.scan_keys(f"{prefix}*"):
            shard_id = int(key.removeprefix(prefix))
            assignments[shard_id] = self.backend.get_members(key)
        return assignments

    def list_worker_heartbeats(self) -> list[WorkerHeartbeat]:
        prefix = f"{self.key_prefix}:worker:"
        suffix = ":heartbeat"
        heartbeats: list[WorkerHeartbeat] = []
        for key in self.backend.scan_keys(f"{prefix}*"):
            if not key.endswith(suffix):
                continue
            raw = self.backend.get(key)
            if raw is None:
                continue
            payload = json.loads(raw)
            heartbeats.append(
                WorkerHeartbeat(
                    worker_id=payload["worker_id"],
                    pod_name=payload["pod_name"],
                    shard_id=int(payload["shard_id"]),
                    status=RuntimeContractState(payload["status"]),
                    owned_symbol_count=int(payload["owned_symbol_count"]),
                    updated_at=datetime.fromisoformat(payload["updated_at"]),
                )
            )
        return heartbeats

    def _assignment_version_key(self) -> str:
        return f"{self.key_prefix}:assignments:version"

    def _assignment_key(self, shard_id: int) -> str:
        return f"{self.key_prefix}:assignments:shard:{shard_id}"

    def _heartbeat_key(self, worker_id: str) -> str:
        return f"{self.key_prefix}:worker:{worker_id}:heartbeat"


def heartbeat_from_runtime(
    *,
    worker_id: str,
    pod_name: str,
    shard_id: int,
    status: RuntimeContractState,
    owned_symbol_count: int,
    updated_at: datetime,
) -> WorkerHeartbeat:
    return WorkerHeartbeat(
        worker_id=worker_id,
        pod_name=pod_name,
        shard_id=shard_id,
        status=status,
        owned_symbol_count=owned_symbol_count,
        updated_at=updated_at,
    )
