from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.constants import SUPPORTED_RESOLUTIONS


DataDownloadJobStatus = Literal["pending", "running", "completed", "failed"]


class DataDownloadRecord(BaseModel):
    symbol: str
    start_date: date
    stop_date: date
    resolution: str = Field(description="Bar resolution such as 1m, 5m, 15m, 1h, or 1d")
    feed: Literal["iex", "sip", "otc"] = "iex"
    force_refresh: bool = False

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        if value not in SUPPORTED_RESOLUTIONS:
            supported = ", ".join(SUPPORTED_RESOLUTIONS)
            raise ValueError(f"resolution must be one of: {supported}")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "DataDownloadRecord":
        if self.start_date > self.stop_date:
            raise ValueError("start_date must be <= stop_date")
        return self


class DataDownloadCreateRequest(BaseModel):
    output_folder: str
    records: list[DataDownloadRecord] = Field(min_length=1)


class DataDownloadCreateResponse(BaseModel):
    job_id: str
    status: Literal["pending"]
    status_url: str
    detail_url: str


class DataDownloadStatusResponse(BaseModel):
    job_id: str
    status: DataDownloadJobStatus
    output_folder: str
    total_records: int
    completed_records: int = 0
    successful_records: int = 0
    failed_records: int = 0
    created_at: datetime
    updated_at: datetime
    error_message: str | None = None


class DataDownloadRecordResult(BaseModel):
    symbol: str
    start_date: date
    stop_date: date
    resolution: str
    feed: str
    cache_status: str | None = None
    parquet_path: str | None = None
    row_count: int | None = None
    error: str | None = None


class DataDownloadDetailResponse(BaseModel):
    metadata: DataDownloadStatusResponse
    records: list[DataDownloadRecordResult]
