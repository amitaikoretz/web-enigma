from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SUPPORTED_DATASET_RESOLUTIONS = ("1m", "5m", "15m", "1h", "1d")
SUPPORTED_DATASET_PROVIDERS = ("alpaca", "yahoo")
DatasetJobStatus = Literal["pending", "running", "completed", "failed"]


class DatasetOptionsRequest(BaseModel):
    enabled: bool = False
    feed: Literal["indicative", "opra"] = "indicative"


class DatasetCreateRequest(BaseModel):
    symbol: str
    provider: Literal["alpaca", "yahoo"]
    resolution: str
    start_date: date
    end_date: date
    name: str | None = None
    options: DatasetOptionsRequest = Field(default_factory=DatasetOptionsRequest)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        symbol = value.strip().upper()
        if not symbol:
            raise ValueError("symbol must not be empty")
        return symbol

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
        return self


class DatasetListItem(BaseModel):
    id: str
    name: str | None = None
    symbol: str
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


class DatasetDetailResponse(BaseModel):
    metadata: DatasetListItem


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
