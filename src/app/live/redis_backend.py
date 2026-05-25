from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import redis


class RedisClientBackend:
    def __init__(self, url: str) -> None:
        self._client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Any:
        return self._client.get(key)

    def set(self, key: str, value: Any) -> None:
        self._client.set(key, value)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def set_members(self, key: str, values: Iterable[str]) -> None:
        members = list(values)
        pipe = self._client.pipeline()
        pipe.delete(key)
        if members:
            pipe.sadd(key, *members)
        pipe.execute()

    def get_members(self, key: str) -> set[str]:
        return set(self._client.smembers(key))

    def scan_keys(self, pattern: str) -> list[str]:
        return sorted(self._client.scan_iter(match=pattern))
