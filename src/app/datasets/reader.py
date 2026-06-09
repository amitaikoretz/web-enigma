from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pandas as pd

from app.datasets.models import DatasetArtifactManifest, DatasetChunkRecord


def _derive_dataset_path_from_manifest_path(manifest_path: Path) -> Path:
    name = manifest_path.name
    if name.endswith(".manifest.json"):
        return manifest_path.with_name(f"{name[: -len('.manifest.json')]}.parquet")
    if manifest_path.suffix:
        return manifest_path.with_suffix(".parquet")
    return manifest_path.with_name(f"{name}.parquet")


class DatasetArtifactReader:
    def __init__(
        self,
        manifest: DatasetArtifactManifest,
        *,
        manifest_path: Path,
        dataset_path: str | Path | None = None,
    ) -> None:
        self._manifest = manifest
        self._manifest_path = manifest_path.resolve()
        self._dataset_path = Path(dataset_path).expanduser() if dataset_path is not None else None

    @classmethod
    def from_manifest_path(
        cls,
        manifest_path: str | Path,
        *,
        dataset_path: str | Path | None = None,
    ) -> "DatasetArtifactReader":
        path = Path(manifest_path)
        manifest = DatasetArtifactManifest.model_validate_json(path.read_text(encoding="utf-8"))
        return cls(manifest, manifest_path=path, dataset_path=dataset_path)

    @property
    def manifest(self) -> DatasetArtifactManifest:
        return self._manifest

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    @property
    def dataset_path(self) -> Path:
        if self._dataset_path is not None:
            return self._dataset_path
        return Path(self._manifest.output_path)

    @property
    def output_path(self) -> Path:
        return Path(self._manifest.output_path)

    @property
    def chunk_count(self) -> int:
        return self._manifest.chunk_count

    @property
    def primary_split_keys(self) -> list[str]:
        return list(self._manifest.primary_split_keys)

    @property
    def fallback_split_keys(self) -> list[str]:
        return list(self._manifest.fallback_split_keys)

    @property
    def chunk_records(self) -> list[DatasetChunkRecord]:
        return list(self._manifest.chunks)

    @property
    def chunk_paths(self) -> list[Path]:
        return [Path(entry.path) for entry in self._manifest.chunks]

    def iter_chunks(self) -> Iterator[tuple[DatasetChunkRecord, pd.DataFrame]]:
        for entry in self._manifest.chunks:
            yield entry, pd.read_parquet(entry.path)

    def load_chunk(self, chunk_index: int) -> pd.DataFrame:
        try:
            entry = self._manifest.chunks[chunk_index]
        except IndexError as exc:
            raise IndexError(f"Chunk index {chunk_index} out of range") from exc
        return pd.read_parquet(entry.path)

    def _candidate_dataset_paths(self) -> list[Path]:
        candidates: list[Path] = []
        if self._dataset_path is not None:
            candidates.append(self._dataset_path)
        candidates.append(Path(self._manifest.output_path))
        candidates.append(_derive_dataset_path_from_manifest_path(self._manifest_path))

        unique_candidates: list[Path] = []
        for candidate in candidates:
            if candidate not in unique_candidates:
                unique_candidates.append(candidate)
        return unique_candidates

    def _resolve_dataset_path(self) -> Path | None:
        for candidate in self._candidate_dataset_paths():
            if candidate.is_file():
                return candidate
        return None

    def load(self) -> pd.DataFrame:
        dataset_path = self._resolve_dataset_path()
        if dataset_path is not None:
            return pd.read_parquet(dataset_path)

        frames: list[pd.DataFrame] = []
        missing_chunk_paths: list[str] = []
        for entry in self._manifest.chunks:
            chunk_path = Path(entry.path)
            if not chunk_path.is_file():
                missing_chunk_paths.append(str(chunk_path))
                continue
            frames.append(pd.read_parquet(chunk_path))

        if frames and not missing_chunk_paths:
            return pd.concat(frames, ignore_index=True)

        missing_parts = []
        if missing_chunk_paths:
            missing_parts.append(f"missing chunk files: {', '.join(missing_chunk_paths)}")
        else:
            missing_parts.append("no readable dataset parquet or chunk parquet files were found")
        raise FileNotFoundError(
            f"Unable to load dataset artifact from {self.manifest_path}: {'; '.join(missing_parts)}"
        )
