from __future__ import annotations

import math
import hashlib
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.datasets.models import SUPPORTED_DATASET_PROVIDERS, SUPPORTED_DATASET_RESOLUTIONS

_DATASET_PLAN_VERSION = "dataset-shard-plan-v1"
_DATASET_MANIFEST_VERSION = "dataset-artifact-manifest-v1"
_DEFAULT_TARGET_WORK_UNITS = 5_000
_DEFAULT_MAX_SHARDS = 8
_DEFAULT_MAX_PODS = 4

_RESOLUTION_WEIGHT = {
    "1m": 60,
    "5m": 12,
    "15m": 4,
    "1h": 1,
    "1d": 1,
}


class DatasetChunkRecord(BaseModel):
    path: str
    row_count: int = Field(ge=0)
    size_bytes: int = Field(ge=0)
    chunk_index: int = Field(ge=0)
    split_key_values: dict[str, str] = Field(default_factory=dict)


class DatasetArtifactManifest(BaseModel):
    manifest_version: str = _DATASET_MANIFEST_VERSION
    dataset_kind: Literal["market", "options"]
    dataset_id: str
    symbols: list[str] = Field(default_factory=list)
    provider: str
    resolution: str
    start_date: date
    end_date: date
    output_path: str
    plan_path: str
    primary_split_keys: list[str] = Field(default_factory=lambda: ["symbol"])
    fallback_split_keys: list[str] = Field(default_factory=lambda: ["timestamp"])
    estimated_total_work_units: int = Field(ge=0)
    shard_count: int = Field(ge=1)
    chunk_count: int = Field(ge=0)
    total_row_count: int = Field(ge=0)
    total_size_bytes: int = Field(ge=0)
    chunks: list[DatasetChunkRecord] = Field(default_factory=list)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            symbol = value.strip().upper()
            if symbol and symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @model_validator(mode="after")
    def validate_chunks(self) -> "DatasetArtifactManifest":
        if self.chunk_count != len(self.chunks):
            raise ValueError("chunk_count must match the number of chunks")
        if self.total_row_count < 0 or self.total_size_bytes < 0:
            raise ValueError("manifest totals must be non-negative")
        return self


class DatasetShardSpec(BaseModel):
    shard_id: str
    shard_index: int = Field(ge=0)
    shard_count: int = Field(ge=1)
    symbols: list[str] = Field(default_factory=list)
    symbols_csv: str = ""
    symbol_count: int = Field(ge=0)
    output_dir: str
    progress_total_units: int = Field(ge=1)
    progress_symbol_units: int = Field(ge=1)
    market_parquet_path: str
    market_manifest_path: str
    options_parquet_path: str | None = None
    options_manifest_path: str | None = None
    work_units: int = Field(ge=1)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            symbol = value.strip().upper()
            if symbol and symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @model_validator(mode="after")
    def validate_symbol_count(self) -> "DatasetShardSpec":
        if self.symbol_count != len(self.symbols):
            raise ValueError("symbol_count must match the number of symbols")
        expected_csv = ",".join(self.symbols)
        if self.symbols_csv and self.symbols_csv != expected_csv:
            raise ValueError("symbols_csv must match the normalized symbols")
        if not self.symbols_csv:
            self.symbols_csv = expected_csv
        return self


class DatasetShardPlan(BaseModel):
    plan_version: str = _DATASET_PLAN_VERSION
    dataset_id: str
    symbol: str
    symbols: list[str] = Field(default_factory=list)
    provider: str
    resolution: str
    start_date: date
    end_date: date
    options_enabled: bool
    options_feed: str
    output_dir: str
    plan_path: str
    dataset_output_path: str
    dataset_manifest_path: str
    options_output_path: str | None = None
    options_manifest_path: str | None = None
    primary_split_keys: list[str] = Field(default_factory=lambda: ["symbol"])
    fallback_split_keys: list[str] = Field(default_factory=lambda: ["timestamp"])
    estimated_total_work_units: int = Field(ge=0)
    base_symbol_work_units: int = Field(ge=1)
    download_weight_units: int = Field(ge=1)
    combine_weight_units: int = Field(ge=1)
    max_shards: int = Field(ge=1)
    max_pods: int = Field(ge=1)
    shard_count: int = Field(ge=1)
    parallelism: int = Field(ge=1)
    shards: list[DatasetShardSpec] = Field(default_factory=list)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            symbol = value.strip().upper()
            if symbol and symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @model_validator(mode="after")
    def validate_shards(self) -> "DatasetShardPlan":
        if self.shard_count != len(self.shards):
            raise ValueError("shard_count must match the number of shards")
        if self.parallelism > self.max_pods:
            raise ValueError("parallelism must not exceed max_pods")
        if self.shard_count > self.max_shards:
            raise ValueError("shard_count must not exceed max_shards")
        if self.symbols and self.symbol != self.symbols[0]:
            raise ValueError("symbol must be the primary symbol")
        return self


def normalize_dataset_symbols(symbols: list[str]) -> list[str]:
    normalized: list[str] = []
    for value in symbols:
        symbol = value.strip().upper()
        if symbol and symbol not in normalized:
            normalized.append(symbol)
    return normalized


def dataset_slug(symbols: list[str]) -> str:
    normalized = normalize_dataset_symbols(symbols)
    if not normalized:
        return "dataset"
    if len(normalized) <= 3:
        return "-".join(normalized)
    digest = hashlib.sha1(",".join(normalized).encode("utf-8")).hexdigest()
    return digest[:12]


def resolution_weight(resolution: str) -> int:
    if resolution not in SUPPORTED_DATASET_RESOLUTIONS:
        supported = ", ".join(SUPPORTED_DATASET_RESOLUTIONS)
        raise ValueError(f"resolution must be one of: {supported}")
    return _RESOLUTION_WEIGHT[resolution]


def estimate_symbol_work_units(
    *,
    symbol_count: int,
    resolution: str,
    start_date: date,
    end_date: date,
    options_enabled: bool,
) -> int:
    if symbol_count <= 0:
        return 0
    days_span = max(1, (end_date - start_date).days + 1)
    per_symbol = days_span * resolution_weight(resolution)
    if options_enabled:
        per_symbol *= 2
    return symbol_count * per_symbol


def estimate_dataset_shard_count(
    *,
    symbol_count: int,
    resolution: str,
    start_date: date,
    end_date: date,
    options_enabled: bool,
    max_shards: int = _DEFAULT_MAX_SHARDS,
    target_work_units: int = _DEFAULT_TARGET_WORK_UNITS,
) -> int:
    if symbol_count <= 0:
        return 1
    total_work_units = estimate_symbol_work_units(
        symbol_count=symbol_count,
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        options_enabled=options_enabled,
    )
    if total_work_units <= 0:
        return 1
    estimated = math.ceil(total_work_units / max(1, target_work_units))
    return max(1, min(symbol_count, max_shards, estimated))


def _build_symbol_groups(symbols: list[str], shard_count: int) -> list[list[str]]:
    shard_count = max(1, shard_count)
    groups: list[list[str]] = [[] for _ in range(shard_count)]
    loads = [0 for _ in range(shard_count)]
    for symbol in sorted(normalize_dataset_symbols(symbols)):
        index = min(range(shard_count), key=lambda idx: (loads[idx], len(groups[idx]), idx))
        groups[index].append(symbol)
        loads[index] += 1
    return [group for group in groups if group]


def _shard_work_units(
    *,
    symbol_count: int,
    resolution: str,
    start_date: date,
    end_date: date,
    options_enabled: bool,
) -> tuple[int, int]:
    days_span = max(1, (end_date - start_date).days + 1)
    per_symbol = days_span * resolution_weight(resolution)
    if options_enabled:
        per_symbol *= 2
    total = max(1, symbol_count * per_symbol)
    return per_symbol, total


def build_dataset_shard_plan(
    *,
    dataset_id: str,
    symbols: list[str],
    provider: str,
    resolution: str,
    start_date: date,
    end_date: date,
    options_enabled: bool,
    options_feed: str,
    output_dir: str | Path,
    max_shards: int = _DEFAULT_MAX_SHARDS,
    max_pods: int = _DEFAULT_MAX_PODS,
    target_work_units: int = _DEFAULT_TARGET_WORK_UNITS,
) -> DatasetShardPlan:
    normalized_symbols = normalize_dataset_symbols(symbols)
    if not normalized_symbols:
        raise ValueError("At least one symbol must be provided")
    if provider.strip().lower() not in SUPPORTED_DATASET_PROVIDERS:
        supported = ", ".join(SUPPORTED_DATASET_PROVIDERS)
        raise ValueError(f"provider must be one of: {supported}")

    work_dir = Path(output_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    dataset_slug_value = dataset_slug(normalized_symbols)
    dataset_output_path = str(work_dir / f"{dataset_slug_value}-{provider.strip().lower()}-{resolution}.parquet")
    dataset_manifest_path = str(work_dir / f"{dataset_slug_value}-{provider.strip().lower()}-{resolution}.manifest.json")
    options_output_path = (
        str(work_dir / f"{dataset_slug_value}-alpaca-options-{resolution}.parquet")
        if options_enabled
        else None
    )
    options_manifest_path = (
        str(work_dir / f"{dataset_slug_value}-alpaca-options-{resolution}.manifest.json")
        if options_enabled
        else None
    )

    shard_count = estimate_dataset_shard_count(
        symbol_count=len(normalized_symbols),
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        options_enabled=options_enabled,
        max_shards=max_shards,
        target_work_units=target_work_units,
    )
    shard_groups = _build_symbol_groups(normalized_symbols, shard_count)
    parallelism = max(1, min(max_pods, len(shard_groups)))
    base_symbol_work_units, estimated_total_work_units = _shard_work_units(
        symbol_count=len(normalized_symbols),
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        options_enabled=options_enabled,
    )
    shards_dir = work_dir / "shards"
    shards_dir.mkdir(parents=True, exist_ok=True)

    shards: list[DatasetShardSpec] = []
    for shard_index, shard_symbols in enumerate(shard_groups):
        shard_id = f"shard-{shard_index:03d}"
        shard_output_dir = shards_dir / shard_id
        market_parquet_path = shard_output_dir / "market.parquet"
        market_manifest = shard_output_dir / "market.manifest.json"
        options_parquet_path = shard_output_dir / "options.parquet" if options_enabled else None
        options_manifest = shard_output_dir / "options.manifest.json" if options_enabled else None
        symbol_count = len(shard_symbols)
        work_units = max(1, symbol_count * base_symbol_work_units)
        shards.append(
            DatasetShardSpec(
                shard_id=shard_id,
                shard_index=shard_index,
                shard_count=len(shard_groups),
                symbols=shard_symbols,
                symbols_csv=",".join(shard_symbols),
                symbol_count=symbol_count,
                output_dir=str(shard_output_dir),
                progress_total_units=work_units,
                progress_symbol_units=max(1, base_symbol_work_units),
                market_parquet_path=str(market_parquet_path),
                market_manifest_path=str(market_manifest),
                options_parquet_path=str(options_parquet_path) if options_parquet_path is not None else None,
                options_manifest_path=str(options_manifest) if options_manifest is not None else None,
                work_units=work_units,
            )
        )

    return DatasetShardPlan(
        dataset_id=dataset_id,
        symbol=normalized_symbols[0],
        symbols=normalized_symbols,
        provider=provider.strip().lower(),
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        options_enabled=options_enabled,
        options_feed=options_feed,
        output_dir=str(work_dir),
        plan_path=str(work_dir / "shard-plan.json"),
        dataset_output_path=dataset_output_path,
        dataset_manifest_path=dataset_manifest_path,
        options_output_path=options_output_path,
        options_manifest_path=options_manifest_path,
        estimated_total_work_units=estimated_total_work_units,
        base_symbol_work_units=base_symbol_work_units,
        download_weight_units=estimated_total_work_units,
        combine_weight_units=max(1, len(shards)),
        max_shards=max_shards,
        max_pods=max_pods,
        shard_count=len(shards),
        parallelism=parallelism,
        shards=shards,
    )


def write_json_file(path: Path, payload: BaseModel | dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, BaseModel):
        path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    else:
        import json

        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
