from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd

from app.risk.models import RiskDatasetChunkRecord, RiskDatasetManifest


class RiskDatasetReader:
    def __init__(self, manifest: RiskDatasetManifest, *, manifest_path: Path):
        self._manifest = manifest
        self._manifest_path = manifest_path.resolve()

    @classmethod
    def from_manifest_path(cls, manifest_path: str | Path) -> "RiskDatasetReader":
        path = Path(manifest_path)
        manifest = RiskDatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
        return cls(manifest, manifest_path=path)

    @property
    def manifest(self) -> RiskDatasetManifest:
        return self._manifest

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    @property
    def output_path(self) -> Path:
        return Path(self._manifest.output_path)

    @property
    def primary_split_keys(self) -> list[str]:
        return list(self._manifest.primary_split_keys)

    @property
    def fallback_split_keys(self) -> list[str]:
        return list(self._manifest.fallback_split_keys)

    @property
    def chunk_count(self) -> int:
        return self._manifest.chunk_count

    @property
    def chunk_records(self) -> list[RiskDatasetChunkRecord]:
        return list(self._manifest.files)

    @property
    def chunk_paths(self) -> list[Path]:
        return [self.resolve_chunk_path(entry) for entry in self._manifest.files]

    def resolve_chunk_path(self, entry: RiskDatasetChunkRecord) -> Path:
        raw_path = Path(entry.path)
        if raw_path.is_file():
            return raw_path
        
        parts = raw_path.parts
        if "chunks" in parts:
            idx = parts.index("chunks")
            relative_chunk_path = Path(*parts[idx:])
            candidate = self._manifest_path.parent / relative_chunk_path
            if candidate.is_file():
                return candidate

        candidate_direct = self._manifest_path.parent / raw_path.name
        if candidate_direct.is_file():
            return candidate_direct

        return raw_path

    def iter_chunks(self) -> Iterator[tuple[RiskDatasetChunkRecord, pd.DataFrame]]:
        for entry in self._manifest.files:
            yield entry, pd.read_parquet(self.resolve_chunk_path(entry))

    def load_chunk(self, chunk_index: int) -> pd.DataFrame:
        try:
            entry = self._manifest.files[chunk_index]
        except IndexError as exc:
            raise IndexError(f"Chunk index {chunk_index} out of range") from exc
        return pd.read_parquet(self.resolve_chunk_path(entry))

    def load(self) -> pd.DataFrame:
        frames = [frame for _, frame in self.iter_chunks()]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def _matches_split_values(self, entry: RiskDatasetChunkRecord, split_key_values: dict[str, str]) -> bool:
        for key, value in split_key_values.items():
            if entry.split_key_values.get(key) != value:
                return False
        return True

    def find_chunks(self, **split_key_values: str) -> list[RiskDatasetChunkRecord]:
        return [entry for entry in self._manifest.files if self._matches_split_values(entry, split_key_values)]

    def load_for_split(self, **split_key_values: str) -> pd.DataFrame:
        entries = self.find_chunks(**split_key_values)
        if not entries:
            raise KeyError(f"No dataset chunks match split key values: {split_key_values}")
        frames = [pd.read_parquet(self.resolve_chunk_path(entry)) for entry in entries]
        return pd.concat(frames, ignore_index=True) if len(frames) > 1 else frames[0]

