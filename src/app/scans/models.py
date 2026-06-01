from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

ScanType = Literal["momentum", "options", "trend"]
ScanStatus = Literal["pending", "running", "completed", "failed"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ScanCreateRequest(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)


class ScanCreateResponse(BaseModel):
    scan_id: str


class ScanStatusResponse(BaseModel):
    scan_id: str
    scan_type: ScanType
    status: ScanStatus
    created_at: datetime
    updated_at: datetime
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    results_json_path: str | None = None

    error_exception: str | None = None
    error_code_location: str | None = None
    error_call_stack: str | None = None
    error_traceback: str | None = None


class ScanListResponse(BaseModel):
    items: list[ScanStatusResponse]

