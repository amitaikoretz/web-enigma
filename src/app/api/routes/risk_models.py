from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import ApiDependencies, get_deps
from app.risk.models_api import (
    RiskModelCreateRequest,
    RiskModelCreateResponse,
    RiskModelDetailResponse,
    RiskModelListItemResponse,
    RiskModelStatusResponse,
)
from app.risk.service import RiskModelValidationError


router = APIRouter(prefix="/risk-models", tags=["risk-models"])


@router.post("", response_model=RiskModelCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_risk_model(
    payload: RiskModelCreateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> RiskModelCreateResponse:
    try:
        result = deps.risk_models.create_and_submit_argo(payload)
        return RiskModelCreateResponse(
            group_id=result.group_id,
            status="running",
            argo_namespace=result.argo_namespace,
            argo_workflow_name=result.argo_workflow_name,
        )
    except RiskModelValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=list[RiskModelListItemResponse])
def list_risk_models(
    deps: ApiDependencies = Depends(get_deps),
) -> list[RiskModelListItemResponse]:
    items = deps.risk_models_repo.list_recent(limit=200)
    return [
        RiskModelListItemResponse(
            group_id=i.group_id,
            created_at=i.created_at,
            updated_at=i.updated_at,
            status=i.status,  # type: ignore[arg-type]
            argo_namespace=i.argo_namespace,
            argo_workflow_name=i.argo_workflow_name,
            backtest_ids=i.backtest_ids,
            targets=i.targets,
            summary_metrics=i.summary_metrics,
            artifact_dir=i.artifact_dir,
        )
        for i in items
    ]


@router.get("/{group_id}", response_model=RiskModelDetailResponse)
def get_risk_model(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> RiskModelDetailResponse:
    detail = deps.risk_models_repo.get_detail(group_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Risk model '{group_id}' not found")
    return RiskModelDetailResponse(
        group_id=detail.group_id,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        status=detail.status,  # type: ignore[arg-type]
        argo_namespace=detail.argo_namespace,
        argo_workflow_name=detail.argo_workflow_name,
        params=detail.params,
        artifact_dir=detail.artifact_dir,
        summary_metrics=detail.summary_metrics,
        sources=detail.sources,
        targets=[
            {
                "id": t.id,
                "group_id": t.group_id,
                "target_key": t.target_key,
                "task_type": t.task_type,
                "status": t.status,
                "model_artifact_path": t.model_artifact_path,
                "metrics": t.metrics,
                "dataset_manifest_path": t.dataset_manifest_path,
                "feature_columns": t.feature_columns,
                "created_at": t.created_at,
                "updated_at": t.updated_at,
            }
            for t in detail.targets
        ],
    )


@router.get("/{group_id}/status", response_model=RiskModelStatusResponse)
def get_risk_model_status(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> RiskModelStatusResponse:
    detail = deps.risk_models_repo.get_detail(group_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Risk model '{group_id}' not found")
    phase = deps.risk_models.get_argo_phase(group_id)
    return RiskModelStatusResponse(
        group_id=detail.group_id,
        status=detail.status,  # type: ignore[arg-type]
        argo_namespace=detail.argo_namespace,
        argo_workflow_name=detail.argo_workflow_name,
        argo_phase=phase,
    )

