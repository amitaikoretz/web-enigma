from __future__ import annotations

from datetime import date, datetime
from typing import Literal

import pandas as pd
import pyarrow as pa
from pydantic import BaseModel, Field, TypeAdapter, ConfigDict, field_validator, model_validator

SUPPORTED_DATASET_RESOLUTIONS = ("1m", "5m", "15m", "1h", "1d")
SUPPORTED_DATASET_PROVIDERS = ("alpaca", "yahoo")
DatasetJobStatus = Literal["pending", "running", "completed", "failed"]


class DatasetOptionsRequest(BaseModel):
    enabled: bool = False
    feed: Literal["indicative", "opra"] = "indicative"


class DatasetCreateRequest(BaseModel):
    symbol: str | None = None
    symbols: list[str] = Field(default_factory=list)
    max_symbols_per_shard: int = Field(default=10, ge=1)
    provider: Literal["alpaca", "yahoo"]
    resolution: str
    start_date: date
    end_date: date
    name: str | None = None
    options: DatasetOptionsRequest = Field(default_factory=DatasetOptionsRequest)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        if value is None:
            return None
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("symbol must not be empty")
        return symbol

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, values: object) -> list[str]:
        if values is None:
            return []
        if not isinstance(values, list):
            raise TypeError("symbols must be a list")
        normalized: list[str] = []
        for value in values:
            if not isinstance(value, str):
                raise TypeError("symbols must contain strings")
            symbol = value.strip().upper()
            if not symbol:
                raise ValueError("symbols must not contain empty values")
            if symbol not in normalized:
                normalized.append(symbol)
        return normalized

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        if value not in SUPPORTED_DATASET_RESOLUTIONS:
            supported = ", ".join(SUPPORTED_DATASET_RESOLUTIONS)
            raise ValueError(f"resolution must be one of: {supported}")
        return value

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("name must be a string")
        trimmed = value.strip()
        return trimmed or None

    @model_validator(mode="after")
    def validate_dates(self) -> "DatasetCreateRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        if not self.symbols and self.symbol is None:
            raise ValueError("symbols must not be empty")
        if self.symbols and self.symbol is None:
            self.symbol = self.symbols[0]
        elif self.symbol is not None and not self.symbols:
            self.symbols = [self.symbol]
        elif self.symbol is not None and self.symbols and self.symbols[0] != self.symbol:
            if self.symbol not in self.symbols:
                self.symbols = [self.symbol, *self.symbols]
            else:
                self.symbols = [self.symbol, *[item for item in self.symbols if item != self.symbol]]
        return self


class DatasetListItem(BaseModel):
    id: str
    name: str | None = None
    symbol: str
    symbols: list[str] = Field(default_factory=list)
    provider: str
    resolution: str
    start_date: date
    end_date: date
    created_at: datetime
    updated_at: datetime
    status: DatasetJobStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    params_json: dict = Field(default_factory=dict)
    output_dir: str
    dataset_parquet_path: str | None = None
    manifest_path: str | None = None
    options_parquet_path: str | None = None
    options_manifest_path: str | None = None
    error_message: str | None = None
    progress_pct: float = 0.0


class DatasetParquetRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    symbol: str = Field(min_length=1)
    open: float = Field(alias="Open")
    high: float = Field(alias="High")
    low: float = Field(alias="Low")
    close: float = Field(alias="Close")
    volume: int = Field(alias="Volume")

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        timestamp = pd.Timestamp(value)
        if timestamp.tz is None:
            timestamp = timestamp.tz_localize("UTC")
        else:
            timestamp = timestamp.tz_convert("UTC")
        if any((timestamp.second, timestamp.microsecond, timestamp.nanosecond)):
            raise ValueError("timestamp must be aligned to the minute")
        return timestamp.to_pydatetime()


_DATASET_PARQUET_ROWS = TypeAdapter(list[DatasetParquetRow])
_DATASET_PARQUET_SCHEMA = pa.schema(
    [
        pa.field("timestamp", pa.timestamp("ns", tz="UTC")),
        pa.field("symbol", pa.string()),
        pa.field("Open", pa.float64()),
        pa.field("High", pa.float64()),
        pa.field("Low", pa.float64()),
        pa.field("Close", pa.float64()),
        pa.field("Volume", pa.int64()),
    ]
)


def dataset_parquet_schema() -> pa.Schema:
    return _DATASET_PARQUET_SCHEMA


def normalize_dataset_parquet_frame(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()

    if "timestamp" not in out.columns:
        if "datetime" in out.columns:
            out = out.rename(columns={"datetime": "timestamp"})
        else:
            index_name = out.index.name or "index"
            out = out.reset_index().rename(columns={index_name: "timestamp"})

    if "timestamp" not in out.columns:
        raise ValueError("Dataset parquet frame must include a timestamp column")

    out["timestamp"] = pd.to_datetime(out["timestamp"], utc=True, errors="raise").dt.floor("min")

    required_float_columns = ("Open", "High", "Low", "Close")
    for column in required_float_columns:
        if column not in out.columns:
            raise ValueError(f"Dataset parquet frame missing required column '{column}'")
        out[column] = pd.to_numeric(out[column], errors="raise").astype("float64")

    if "Volume" not in out.columns:
        raise ValueError("Dataset parquet frame missing required column 'Volume'")
    volume = pd.to_numeric(out["Volume"], errors="raise")
    if volume.isna().any():
        raise ValueError("Dataset parquet Volume column must not contain null values")
    if not volume.eq(volume.round()).all():
        raise ValueError("Dataset parquet Volume column must contain whole numbers")
    out["Volume"] = volume.astype("int64")

    if "symbol" not in out.columns:
        raise ValueError("Dataset parquet frame missing required column 'symbol'")

    extra_columns = [
        column
        for column in out.columns
        if column not in {"timestamp", "symbol", "Open", "High", "Low", "Close", "Volume"}
    ]
    if extra_columns:
        raise ValueError(f"Dataset parquet frame has unexpected columns: {sorted(extra_columns)}")

    ordered_columns = ["timestamp", "symbol", "Open", "High", "Low", "Close", "Volume"]
    return out[ordered_columns]


def validate_dataset_parquet_frame(frame: pd.DataFrame) -> None:
    normalized = normalize_dataset_parquet_frame(frame)
    _DATASET_PARQUET_ROWS.validate_python(normalized.to_dict(orient="records"))


from app.datasets.sharding import (  # noqa: E402  (re-export shard manifest models)
    DatasetArtifactManifest,
    DatasetChunkRecord,
    DatasetShardPlan,
    DatasetShardSpec,
)


class DatasetStatusResponse(DatasetListItem):
    is_terminal: bool
    argo_phase: str | None = None


class DatasetListPageResponse(BaseModel):
    items: list[DatasetListItem]
    total: int
    page: int
    page_size: int


class DatasetCreateResponse(BaseModel):
    dataset_id: str
    status: DatasetJobStatus
    status_url: str
    detail_url: str


class DatasetArtifactChunkSummary(BaseModel):
    chunk_count: int = Field(ge=1)
    chunk_dir: str = Field(min_length=1)


class DatasetDetailResponse(BaseModel):
    metadata: DatasetListItem
    symbol_options: list[str] = Field(default_factory=list)
    market_chunks: DatasetArtifactChunkSummary | None = None
    options_chunks: DatasetArtifactChunkSummary | None = None


class DatasetWorkflowErrorResponse(BaseModel):
    dataset_id: str
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    argo_phase: str | None = None
    available: bool = False
    status_message: str | None = None
    failed_node_name: str | None = None
    failed_template_name: str | None = None
    error_exception: str | None = None
    error_code_location: str | None = None
    error_call_stack: list[str] = Field(default_factory=list)
    error_traceback: str | None = None
