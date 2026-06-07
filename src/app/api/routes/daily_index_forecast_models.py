from __future__ import annotations

import json
from pathlib import Path
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import ApiDependencies, get_deps
from app.feature_importance.io import load_feature_importance_artifact
from app.feature_importance.models import FeatureImportanceTarget
from app.daily_index_forecast.models import (
    DailyIndexForecastCreateRequest,
    DailyIndexForecastCreateResponse,
    DailyIndexForecastChartResponse,
    DailyIndexForecastDatasetManifestSummary,
    DailyIndexForecastDetailResponse,
    DailyIndexForecastListItemResponse,
    DailyIndexForecastStatusResponse,
    DailyIndexForecastUpdateRequest,
    DailyIndexForecastWorkflowErrorResponse,
)
from app.daily_index_forecast.charts import build_daily_index_forecast_chart_data
from app.daily_index_forecast.persistence import DailyIndexModelDetail as DailyIndexModelDetailRecord
from app.daily_index_forecast.persistence import DailyIndexModelListItem as DailyIndexModelListItemRecord
from app.daily_index_forecast.service import DailyIndexForecastValidationError


router = APIRouter(prefix="/daily-index-forecast-models", tags=["daily-index-forecast-models"])


def _load_manifest_summary(path: str | None) -> DailyIndexForecastDatasetManifestSummary | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
        return DailyIndexForecastDatasetManifestSummary.model_validate(payload)
    except Exception:
        return None


def _resolve_existing_path(*candidates: str | None) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.exists():
            return str(path)
    return None


def _load_feature_importance_for_path(*candidates: str | None):
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_dir():
            path = path / "feature_importance.json"
        else:
            path = path.with_name("feature_importance.json")
        importance = load_feature_importance_artifact(path)
        if importance is not None and importance.targets:
            return importance.targets[0]
    return None


def _detail_response(detail: DailyIndexModelDetailRecord) -> DailyIndexForecastDetailResponse:
    feature_run = detail.feature_run
    feature_run_response = None
    manifest = None
    feature_importance = _load_feature_importance_for_path(detail.artifact_dir)
    if feature_run is not None:
        manifest = _load_manifest_summary(feature_run.manifest_path)
        feature_run_response = {
            "feature_run_id": feature_run.feature_run_id,
            "status": feature_run.status,
            "argo_namespace": feature_run.argo_namespace,
            "argo_workflow_name": feature_run.argo_workflow_name,
            "symbol": feature_run.symbol,
            "benchmark_symbol": feature_run.benchmark_symbol,
            "decision_times": feature_run.decision_times,
            "start_date": feature_run.start_date,
            "end_date": feature_run.end_date,
            "params": feature_run.params,
            "artifact_dir": feature_run.artifact_dir,
            "manifest": manifest,
            "summary_metrics": feature_run.summary_metrics,
            "features_parquet_path": feature_run.features_parquet_path,
            "labels_parquet_path": feature_run.labels_parquet_path,
            "created_at": feature_run.created_at,
            "updated_at": feature_run.updated_at,
        }
    if manifest is None and detail.targets:
        for target in detail.targets:
            manifest = _load_manifest_summary(target.dataset_manifest_path)
            if manifest is not None:
                break
    target_importances: dict[str, FeatureImportanceTarget] = {}
    for target in detail.targets:
        target_importance = _load_feature_importance_for_path(target.model_artifact_path, detail.artifact_dir)
        if target_importance is not None:
            target_importances[target.target_key] = target_importance
            if feature_importance is None:
                feature_importance = target_importance
    return DailyIndexForecastDetailResponse(
        group_id=detail.group_id,
        feature_run_id=detail.feature_run_id,
        name=detail.name,
        created_at=detail.created_at,
        updated_at=detail.updated_at,
        status=detail.status,  # type: ignore[arg-type]
        argo_namespace=detail.argo_namespace,
        argo_workflow_name=detail.argo_workflow_name,
        params=detail.params,
        artifact_dir=detail.artifact_dir,
        summary_metrics=detail.summary_metrics,
        feature_run=feature_run_response,
        dataset_manifest=manifest,
        targets=[
            {
                "id": target.id,
                "group_id": target.group_id,
                "target_key": target.target_key,
                "task_type": target.task_type,
                "status": target.status,
                "model_artifact_path": target.model_artifact_path,
                "metrics": target.metrics,
                "dataset_manifest_path": target.dataset_manifest_path,
                "feature_columns": target.feature_columns,
                "feature_importance": target_importances.get(target.target_key),
                "created_at": target.created_at,
                "updated_at": target.updated_at,
            }
            for target in detail.targets
        ],
        feature_importance=feature_importance,
    )


@router.post("", response_model=DailyIndexForecastCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_daily_index_forecast_model(
    payload: DailyIndexForecastCreateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> DailyIndexForecastCreateResponse:
    try:
        result = deps.daily_index_forecast_models.create_and_submit_argo(payload)
        return DailyIndexForecastCreateResponse(
            group_id=result.group_id,
            feature_run_id=result.feature_run_id,
            name=result.name,
            status="running",
            argo_namespace=result.argo_namespace,
            argo_workflow_name=result.argo_workflow_name,
        )
    except DailyIndexForecastValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch("/{group_id}", response_model=DailyIndexForecastDetailResponse)
def update_daily_index_forecast_model(
    group_id: str,
    payload: DailyIndexForecastUpdateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> DailyIndexForecastDetailResponse:
    try:
        detail = deps.daily_index_forecast_models.update_group_name(group_id, payload.name)
    except DailyIndexForecastValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Daily Index Forecast '{group_id}' not found")
    return _detail_response(detail)


@router.post("/{group_id}/retry", response_model=DailyIndexForecastCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_daily_index_forecast_model(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> DailyIndexForecastCreateResponse:
    try:
        result = deps.daily_index_forecast_models.retry_group(group_id)
        return DailyIndexForecastCreateResponse(
            group_id=result.group_id,
            feature_run_id=result.feature_run_id,
            name=result.name,
            status="running",
            argo_namespace=result.argo_namespace,
            argo_workflow_name=result.argo_workflow_name,
        )
    except DailyIndexForecastValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=list[DailyIndexForecastListItemResponse])
def list_daily_index_forecast_models(
    deps: ApiDependencies = Depends(get_deps),
) -> list[DailyIndexForecastListItemResponse]:
    items = deps.daily_index_forecast_models_repo.list_recent(limit=200)
    return [
        DailyIndexForecastListItemResponse(
            group_id=item.group_id,
            feature_run_id=item.feature_run_id,
            name=item.name,
            created_at=item.created_at,
            updated_at=item.updated_at,
            status=item.status,  # type: ignore[arg-type]
            argo_namespace=item.argo_namespace,
            argo_workflow_name=item.argo_workflow_name,
            symbol=item.symbol,
            benchmark_symbol=item.benchmark_symbol,
            decision_times=item.decision_times,
            start_date=item.start_date,
            end_date=item.end_date,
            targets=item.targets,
            targets_total=item.targets_total,
            targets_done=item.targets_done,
            summary_metrics=item.summary_metrics,
            artifact_dir=item.artifact_dir,
            feature_run_artifact_dir=item.feature_run_artifact_dir,
        )
        for item in items
    ]


@router.get("/{group_id}", response_model=DailyIndexForecastDetailResponse)
def get_daily_index_forecast_model(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> DailyIndexForecastDetailResponse:
    detail = deps.daily_index_forecast_models_repo.get_detail(group_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Daily Index Forecast '{group_id}' not found")
    return _detail_response(detail)


@router.get("/{group_id}/status", response_model=DailyIndexForecastStatusResponse)
def get_daily_index_forecast_model_status(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> DailyIndexForecastStatusResponse:
    detail = deps.daily_index_forecast_models_repo.get_detail(group_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Daily Index Forecast '{group_id}' not found")
    phase = deps.daily_index_forecast_models.get_argo_phase(group_id)
    progress_pct = deps.daily_index_forecast_models.get_argo_progress_pct(group_id)
    return DailyIndexForecastStatusResponse(
        group_id=detail.group_id,
        feature_run_id=detail.feature_run_id,
        name=detail.name,
        status=detail.status,  # type: ignore[arg-type]
        argo_namespace=detail.argo_namespace,
        argo_workflow_name=detail.argo_workflow_name,
        argo_phase=phase,
        progress_pct=progress_pct if progress_pct is not None else 0.0,
    )


@router.get("/{group_id}/chart-data", response_model=DailyIndexForecastChartResponse)
def get_daily_index_forecast_model_chart_data(
    group_id: str,
    selected_date: date,
    resolution: str = "5m",
    deps: ApiDependencies = Depends(get_deps),
) -> DailyIndexForecastChartResponse:
    detail = deps.daily_index_forecast_models_repo.get_detail(group_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Daily Index Forecast '{group_id}' not found")

    feature_run = detail.feature_run
    if feature_run is None or not detail.targets:
        raise HTTPException(status_code=422, detail="Daily Index Forecast artifacts are not available yet")

    manifest_path = None
    metrics = None
    model_path = None
    for target in detail.targets:
        if model_path is None and target.model_artifact_path:
            model_path = target.model_artifact_path
        if manifest_path is None and target.dataset_manifest_path:
            manifest_path = target.dataset_manifest_path
        if metrics is None and target.metrics:
            metrics = target.metrics
    effective_params = detail.params or (feature_run.params if feature_run else None) or {}
    model_path = _resolve_existing_path(
        model_path,
        str(Path(detail.artifact_dir) / "model.json") if detail.artifact_dir else None,
        str(Path(feature_run.artifact_dir) / "model.json") if feature_run and feature_run.artifact_dir else None,
    )
    manifest_path = _resolve_existing_path(
        manifest_path,
        feature_run.manifest_path if feature_run else None,
        str(Path(feature_run.artifact_dir) / "manifest.json") if feature_run and feature_run.artifact_dir else None,
    )
    try:
        return build_daily_index_forecast_chart_data(
            group_id=group_id,
            selected_date=selected_date,
            resolution=resolution,
            cache_config=deps.cache_config,
            model_path=model_path,
            manifest_path=manifest_path,
            model_params=effective_params,
            metrics=metrics,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{group_id}/workflow-errors", response_model=DailyIndexForecastWorkflowErrorResponse)
def get_daily_index_forecast_model_workflow_errors(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> DailyIndexForecastWorkflowErrorResponse:
    result = deps.daily_index_forecast_models.get_workflow_errors(group_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Daily Index Forecast '{group_id}' not found")
    return DailyIndexForecastWorkflowErrorResponse(
        group_id=result.group_id,
        feature_run_id=result.feature_run_id,
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
def delete_daily_index_forecast_model(
    group_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> None:
    try:
        ok = deps.daily_index_forecast_models.delete_group(group_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not ok:
        raise HTTPException(status_code=404, detail=f"Daily Index Forecast '{group_id}' not found")
