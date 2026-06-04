from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ArgoWorkflowResponse(BaseModel):
    workflow_name: str
    namespace: str
    workflow: dict[str, Any]


class ArgoDebugConfigResponse(BaseModel):
    workflow_name: str
    namespace: str
    pod_name: str
    terminal_command: str
    launch_configuration: dict[str, Any]
    snippet: str


class ArgoPodLogsResponse(BaseModel):
    workflow_name: str
    namespace: str
    pod_name: str
    container_name: str | None
    logs: str
