from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol

import pandas as pd


NORMALIZATION_VERSION = "yahoo-v1"


@dataclass(frozen=True)
class CacheKey:
    source: str
    symbol: str
    interval: str
    start_date: str
    end_date: str
    normalization_version: str = NORMALIZATION_VERSION
    feed: str | None = None

    def stable_id(self) -> str:
        payload = {
            "source": self.source.lower(),
            "symbol": self.symbol.upper(),
            "interval": self.interval,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "normalization_version": self.normalization_version,
        }
        if self.feed is not None:
            payload["feed"] = self.feed.lower()
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:20]


@dataclass(frozen=True)
class CacheReadResult:
    status: str
    frame: pd.DataFrame | None = None


class DataCache(Protocol):
    def get(self, key: CacheKey, max_age: timedelta) -> CacheReadResult: ...
    def put(self, key: CacheKey, frame: pd.DataFrame) -> Path: ...
    def path_for(self, key: CacheKey) -> Path: ...


class ParquetDataCache:
    def __init__(self, directory: Path | str):
        self.directory = Path(directory)

    def path_for(self, key: CacheKey) -> Path:
        return (
            self.directory
            / key.source.lower()
            / key.symbol.upper()
            / key.interval
            / f"{key.start_date}_{key.end_date}_{key.stable_id()}.parquet"
        )

    def get(self, key: CacheKey, max_age: timedelta) -> CacheReadResult:
        path = self.path_for(key)
        if not path.exists():
            return CacheReadResult(status="miss", frame=None)

        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        is_fresh = datetime.now(timezone.utc) - modified <= max_age
        if not is_fresh:
            return CacheReadResult(status="stale_refetch", frame=None)

        return CacheReadResult(status="hit", frame=pd.read_parquet(path))

    def put(self, key: CacheKey, frame: pd.DataFrame) -> Path:
        target = self.path_for(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f"{target.stem}.",
            suffix=".tmp",
            dir=str(target.parent),
            delete=False,
        ) as tmp:
            tmp_path = Path(tmp.name)
        try:
            frame.to_parquet(tmp_path, index=True)
            os.replace(tmp_path, target)
            return target
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)

