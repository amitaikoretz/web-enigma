from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import ApiDependencies, get_deps
from app.return_forecast.models_api import (
    ReturnForecastDatasetManifestSummary,
    ReturnForecastModelCreateRequest,
    ReturnForecastModelCreateResponse,
    ReturnForecastModelDetailResponse,
    ReturnForecastModelListItemResponse,
    ReturnForecastModelUpdateRequest,
    ReturnForecastModelStatusResponse,
    ReturnForecastModelWorkflowErrorResponse,
)
from app.risk.persistence import RiskModelDetail as RiskModelDetailRecord
from app.risk.service import RiskModelValidationError


router = APIRouter(prefix="/return-forecast-models", tags=["return-forecast-models"])


def _load_dataset_manifest_summary(detail: RiskModelDetailRecord):
    manifest_paths = []
    for target in detail.targets:
        manifest_path = getattr(target, "dataset_manifest_path", None)
        if manifest_path:
            manifest_paths.append(str(manifest_path))

    for manifest_path in manifest_paths:
        path = Path(manifest_path)
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return ReturnForecastDatasetManifestSummary.model_validate(payload)
        except Exception:
            continue
    return None


def _detail_response(detail: RiskModelDetailRecord) -> ReturnForecastModelDetailResponse:
    return ReturnForecastModelDetailResponse(
        group_id=detail.group_id,
        name=detail.name,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        status=detail.status,  # type: ignore[arg-type]
        argo_namespace=detail.argo_namespace,
        argo_workflow_name=detail.argo_workflow_name,
        params=detail.params,
        artifact_dir=detail.artifact_dir,
        summary_metrics=detail.summary_metrics,
        dataset_manifest=_load_dataset_manifest_summary(detail),
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
        training_start_date=detail.training_start_date,
        training_end_date=detail.training_end_date,
    )


@router.post("", response_model=ReturnForecastModelCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_return_forecast_model(
    payload: ReturnForecastModelCreateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> ReturnForecastModelCreateResponse:
    try:
        result = deps.return_forecast_models.create_and_submit_argo(payload)
        return ReturnForecastModelCreateResponse(
            group_id=result.group_id,
            name=result.name,
            status="running",
            argo_namespace=result.argo_namespace,
            argo_workflow_name=result.argo_workflow_name,
        )
    except RiskModelValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/{group_id}", response_model=ReturnForecastModelDetailResponse)
def update_return_forecast_model(
    group_id: str,
    payload: ReturnForecastModelUpdateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> ReturnForecastModelDetailResponse:
    try:
        detail = deps.return_forecast_models.update_group_name(group_id, payload.name)
    except RiskModelValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Return forecast model '{group_id}' not found")
    return _detail_response(detail)


@router.post("/{group_id}/retry", response_model=ReturnForecastModelCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_return_forecast_model(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> ReturnForecastModelCreateResponse:
    try:
        result = deps.return_forecast_models.retry_group(group_id)
        return ReturnForecastModelCreateResponse(
            group_id=result.group_id,
            name=result.name,
            status="running",
            argo_namespace=result.argo_namespace,
            argo_workflow_name=result.argo_workflow_name,
        )
    except RiskModelValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=list[ReturnForecastModelListItemResponse])
def list_return_forecast_models(
    deps: ApiDependencies = Depends(get_deps),
) -> list[ReturnForecastModelListItemResponse]:
    items = deps.return_forecast_models_repo.list_recent(limit=200)
    return [
        ReturnForecastModelListItemResponse(
            group_id=i.group_id,
            name=i.name,
            created_at=i.created_at,
            updated_at=i.updated_at,
            status=i.status,  # type: ignore[arg-type]
            argo_namespace=i.argo_namespace,
            argo_workflow_name=i.argo_workflow_name,
            backtest_ids=i.backtest_ids,
            dataset_ids=i.dataset_ids,
            targets=i.targets,
            targets_total=i.targets_total,
            targets_done=i.targets_done,
            summary_metrics=i.summary_metrics,
            artifact_dir=i.artifact_dir,
            training_start_date=i.training_start_date,
            training_end_date=i.training_end_date,
        )
        for i in items
    ]


@router.get("/{group_id}", response_model=ReturnForecastModelDetailResponse)
def get_return_forecast_model(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> ReturnForecastModelDetailResponse:
    detail = deps.return_forecast_models_repo.get_detail(group_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Return forecast model '{group_id}' not found")
    return _detail_response(detail)


@router.get("/{group_id}/status", response_model=ReturnForecastModelStatusResponse)
def get_return_forecast_model_status(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> ReturnForecastModelStatusResponse:
    detail = deps.return_forecast_models_repo.get_detail(group_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Return forecast model '{group_id}' not found")
    phase = deps.return_forecast_models.get_argo_phase(group_id)
    return ReturnForecastModelStatusResponse(
        group_id=detail.group_id,
        name=detail.name,
        status=detail.status,  # type: ignore[arg-type]
        argo_namespace=detail.argo_namespace,
        argo_workflow_name=detail.argo_workflow_name,
        argo_phase=phase,
    )


@router.get("/{group_id}/workflow-errors", response_model=ReturnForecastModelWorkflowErrorResponse)
def get_return_forecast_model_workflow_errors(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> ReturnForecastModelWorkflowErrorResponse:
    result = deps.return_forecast_models.get_workflow_errors(group_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Return forecast model '{group_id}' not found")
    return ReturnForecastModelWorkflowErrorResponse(
        group_id=result.group_id,
        argo_namespace=result.argo_namespace,
        argo_workflow_name=result.argo_workflow_name,
        argo_phase=result.argo_phase,
        available=result.available,
        status_message=result.status_message,
        failed_node_name=result.failed_node_name,
        failed_template_name=result.failed_template_name,
        error_exception=result.error_exception,
        error_code_location=result.error_code_location,
        error_call_stack=result.error_call_stack,
        error_traceback=result.error_traceback,
    )


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_return_forecast_model(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> None:
    try:
        ok = deps.return_forecast_models.delete_group(group_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail=f"Return forecast model '{group_id}' not found")
