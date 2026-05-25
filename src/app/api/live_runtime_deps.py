from __future__ import annotations

import os
from dataclasses import dataclass

from app.live.assignments import RedisAssignmentStore, get_shared_redis_backend
from app.live.control_flags import RedisControlFlagStore
from app.live.leases import RedisLeaseStore


@dataclass(frozen=True)
class LiveRuntimeStores:
    assignment_store: RedisAssignmentStore
    lease_store: RedisLeaseStore
    control_flag_store: RedisControlFlagStore


def get_live_runtime_stores() -> LiveRuntimeStores:
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    key_prefix = os.environ.get("REDIS_KEY_PREFIX", "ta")
    backend = get_shared_redis_backend(redis_url)
    return LiveRuntimeStores(
        assignment_store=RedisAssignmentStore(backend=backend, key_prefix=key_prefix),
        lease_store=RedisLeaseStore(backend=backend, key_prefix=key_prefix),
        control_flag_store=RedisControlFlagStore(backend=backend, key_prefix=key_prefix),
    )
