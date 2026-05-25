from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

from app.contracts import load_active_contracts
from app.live.assignments import AssignmentStore, RedisAssignmentStore, get_shared_redis_backend
from app.live.assignment_publisher import contracts_to_snapshots, publish_assignments_for_contracts
from app.live.revocation import (
    ContractRevocationStore,
    NoopContractRevocationStore,
    RedisContractRevocationStore,
)
from sqlalchemy.orm import Session


@dataclass(frozen=True)
class LiveRuntimeEnvConfig:
    redis_url: str | None
    redis_key_prefix: str
    shard_count: int

    @classmethod
    def from_env(cls) -> "LiveRuntimeEnvConfig":
        redis_url = os.environ.get("LIVE_REDIS_URL")
        if redis_url is not None and not redis_url.strip():
            redis_url = None
        return cls(
            redis_url=redis_url,
            redis_key_prefix=os.environ.get("LIVE_REDIS_KEY_PREFIX", "ta"),
            shard_count=max(1, int(os.environ.get("LIVE_SHARD_COUNT", "2"))),
        )


class ContractMutationService:
    def __init__(
        self,
        *,
        assignment_store: AssignmentStore | None,
        revocation_store: ContractRevocationStore,
        shard_count: int,
    ) -> None:
        self.assignment_store = assignment_store
        self.revocation_store = revocation_store
        self.shard_count = shard_count

    @classmethod
    def from_env(cls) -> "ContractMutationService":
        config = LiveRuntimeEnvConfig.from_env()
        if config.redis_url is None:
            return cls(
                assignment_store=None,
                revocation_store=NoopContractRevocationStore(),
                shard_count=config.shard_count,
            )
        backend = get_shared_redis_backend(config.redis_url)
        return cls(
            assignment_store=RedisAssignmentStore(backend=backend, key_prefix=config.redis_key_prefix),
            revocation_store=RedisContractRevocationStore(backend=backend, key_prefix=config.redis_key_prefix),
            shard_count=config.shard_count,
        )

    def invalidate_contract(self, session: Session, *, contract_id: UUID, revision: int) -> int | None:
        self.revocation_store.revoke_contract(contract_id, revision)
        if self.assignment_store is None:
            return None
        active_contracts = load_active_contracts(session)
        snapshots = contracts_to_snapshots(active_contracts)
        return publish_assignments_for_contracts(
            self.assignment_store,
            snapshots,
            self.shard_count,
        )


_contract_mutation_service: ContractMutationService | None = None


def reset_contract_mutation_service() -> None:
    global _contract_mutation_service
    _contract_mutation_service = None


def get_contract_mutation_service() -> ContractMutationService:
    global _contract_mutation_service
    if _contract_mutation_service is None:
        _contract_mutation_service = ContractMutationService.from_env()
    return _contract_mutation_service
