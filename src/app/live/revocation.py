from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID


class ContractRevocationStore(Protocol):
    def revoke_contract(self, contract_id: UUID, revision: int) -> None: ...

    def is_contract_revoked(self, contract_id: UUID) -> bool: ...


class NoopContractRevocationStore:
    def revoke_contract(self, contract_id: UUID, revision: int) -> None:
        return None

    def is_contract_revoked(self, contract_id: UUID) -> bool:
        return False


class RedisContractRevocationStore:
    def __init__(self, *, backend, key_prefix: str = "ta") -> None:
        self.backend = backend
        self.key_prefix = key_prefix

    def revoke_contract(self, contract_id: UUID, revision: int) -> None:
        payload = {
            "revision": revision,
            "revoked_at": datetime.now(UTC).isoformat(),
        }
        self.backend.set(self._revocation_key(contract_id), json.dumps(payload))

    def is_contract_revoked(self, contract_id: UUID) -> bool:
        return self.backend.get(self._revocation_key(contract_id)) is not None

    def _revocation_key(self, contract_id: UUID) -> str:
        return f"{self.key_prefix}:control:revoked:contract:{contract_id}"
