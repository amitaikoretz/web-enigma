from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ControlFlagsSnapshot:
    kill_switch_enabled: bool
    paused_contracts: list[str] = field(default_factory=list)
    paused_symbols: list[str] = field(default_factory=list)
    paused_shards: list[int] = field(default_factory=list)


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

    def snapshot(self) -> ControlFlagsSnapshot:
        paused_contracts: list[str] = []
        paused_symbols: list[str] = []
        paused_shards: list[int] = []
        prefix = f"{self.key_prefix}:control:pause:"
        for key in self.backend.scan_keys(f"{prefix}*"):
            raw = self.backend.get(key)
            if not _decode_enabled_flag(raw):
                continue
            scope_key = key.removeprefix(prefix)
            if scope_key.startswith("contract:"):
                paused_contracts.append(scope_key.removeprefix("contract:"))
            elif scope_key.startswith("symbol:"):
                paused_symbols.append(scope_key.removeprefix("symbol:"))
            elif scope_key.startswith("shard:"):
                paused_shards.append(int(scope_key.removeprefix("shard:")))
        return ControlFlagsSnapshot(
            kill_switch_enabled=self.is_global_kill_switch_enabled(),
            paused_contracts=sorted(paused_contracts),
            paused_symbols=sorted(paused_symbols),
            paused_shards=sorted(paused_shards),
        )


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
