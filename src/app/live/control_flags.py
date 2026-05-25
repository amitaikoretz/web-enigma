from __future__ import annotations

import json
from typing import Protocol


class ControlFlagStore(Protocol):
    def is_global_kill_switch_enabled(self) -> bool: ...

    def is_contract_paused(self, contract_id: str) -> bool: ...

    def is_symbol_paused(self, symbol_key: str) -> bool: ...

    def is_shard_paused(self, shard_id: int) -> bool: ...


class RedisControlFlagStore:
    def __init__(self, *, backend, key_prefix: str = "ta") -> None:
        self.backend = backend
        self.key_prefix = key_prefix

    def is_global_kill_switch_enabled(self) -> bool:
        raw = self.backend.get(f"{self.key_prefix}:control:kill_switch")
        return _decode_enabled_flag(raw)

    def is_contract_paused(self, contract_id: str) -> bool:
        raw = self.backend.get(f"{self.key_prefix}:control:pause:contract:{contract_id}")
        return _decode_enabled_flag(raw)

    def is_symbol_paused(self, symbol_key: str) -> bool:
        raw = self.backend.get(f"{self.key_prefix}:control:pause:symbol:{symbol_key}")
        return _decode_enabled_flag(raw)

    def is_shard_paused(self, shard_id: int) -> bool:
        raw = self.backend.get(f"{self.key_prefix}:control:pause:shard:{shard_id}")
        return _decode_enabled_flag(raw)


def _decode_enabled_flag(raw: object) -> bool:
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return raw.lower() in {"1", "true", "yes", "on"}
        if isinstance(payload, dict):
            return bool(payload.get("enabled", False))
        if isinstance(payload, bool):
            return payload
    return False
