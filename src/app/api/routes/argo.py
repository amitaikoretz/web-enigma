from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import ApiDependencies, get_deps
from app.api.schemas.argo import ArgoDebugConfigResponse, ArgoPodLogsResponse
from app.argo_inspection import (
    ArgoWorkflowInspectionError,
    ArgoWorkflowInspectionService,
    ArgoWorkflowNotFoundError,
    ArgoWorkflowPodNotFoundError,
)

router = APIRouter(prefix="/argo", tags=["argo"])


def _inspection_service(deps: ApiDependencies) -> ArgoWorkflowInspectionService:
    return ArgoWorkflowInspectionService(submitter=deps.backtest_jobs.argo_submitter)


@router.get("/workflows/{workflow_name}", response_model=dict[str, object])
def get_workflow_json(
    workflow_name: str,
    namespace: str | None = Query(default=None),
    deps: ApiDependencies = Depends(get_deps),
) -> dict[str, object]:
    service = _inspection_service(deps)
    try:
        workflow = service.get_workflow(workflow_name, namespace=namespace)
    except ArgoWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArgoWorkflowInspectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return workflow


@router.get("/workflows/{workflow_name}/pods/{pod_name}/debug-config", response_model=ArgoDebugConfigResponse)
def get_workflow_pod_debug_config(
    workflow_name: str,
    pod_name: str,
    namespace: str | None = Query(default=None),
    deps: ApiDependencies = Depends(get_deps),
) -> ArgoDebugConfigResponse:
    service = _inspection_service(deps)
    try:
        result = service.build_debug_configuration(workflow_name, pod_name, namespace=namespace)
    except ArgoWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArgoWorkflowPodNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArgoWorkflowInspectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ArgoDebugConfigResponse(
        workflow_name=result.workflow_name,
        namespace=result.namespace,
        pod_name=result.pod_name,
        terminal_command=result.terminal_command,
        launch_configuration=result.launch_configuration,
        snippet=result.snippet,
    )


@router.get("/workflows/{workflow_name}/pods/{pod_name}/logs", response_model=ArgoPodLogsResponse)
def get_workflow_pod_logs(
    workflow_name: str,
    pod_name: str,
    namespace: str | None = Query(default=None),
    deps: ApiDependencies = Depends(get_deps),
) -> ArgoPodLogsResponse:
    service = _inspection_service(deps)
    try:
        result = service.get_pod_logs(workflow_name, pod_name, namespace=namespace)
    except ArgoWorkflowNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArgoWorkflowPodNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ArgoWorkflowInspectionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ArgoPodLogsResponse(
        workflow_name=result.workflow_name,
        namespace=result.namespace,
        pod_name=result.pod_name,
        container_name=result.container_name,
        logs=result.logs,
    )
