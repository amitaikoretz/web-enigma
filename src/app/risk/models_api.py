from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RiskModelStatus = Literal["pending", "running", "succeeded", "failed", "canceled"]
RiskModelTaskType = Literal["classification", "regression"]


class RiskModelTargetSpec(BaseModel):
    target_key: str = Field(..., examples=["stop_prob", "mae"])
    task_type: RiskModelTaskType


class RiskModelCreateRequest(BaseModel):
    backtest_ids: list[str]
    targets: list[RiskModelTargetSpec] = Field(default_factory=list)
    dataset_config: dict[str, Any] = Field(default_factory=dict)
    train_config: dict[str, Any] = Field(default_factory=dict)


class RiskModelCreateResponse(BaseModel):
    group_id: str
    status: RiskModelStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None


class RiskModelListItemResponse(BaseModel):
    group_id: str
    created_at: datetime
    updated_at: datetime
    status: RiskModelStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    backtest_ids: list[str] = Field(default_factory=list)
    targets: list[str] = Field(default_factory=list)
    targets_total: int = 0
    targets_done: int = 0
    summary_metrics: dict[str, Any] | None = None
    artifact_dir: str


class RiskModelTargetRowResponse(BaseModel):
    id: int
    group_id: str
    target_key: str
    task_type: RiskModelTaskType | str
    status: RiskModelStatus | str
    model_artifact_path: str | None = None
    metrics: dict[str, Any] | None = None
    dataset_manifest_path: str | None = None
    feature_columns: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class RiskModelDetailResponse(BaseModel):
    group_id: str
    created_at: datetime
    updated_at: datetime
    status: RiskModelStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    artifact_dir: str
    summary_metrics: dict[str, Any] | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    targets: list[RiskModelTargetRowResponse] = Field(default_factory=list)


class RiskModelStatusResponse(BaseModel):
    group_id: str
    status: RiskModelStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    argo_phase: str | None = None


class RiskModelWorkflowErrorResponse(BaseModel):
    group_id: str
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
