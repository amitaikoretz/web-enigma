from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse

from app.api.deps import ApiDependencies, get_deps
from app.datasets import (
    DatasetCreateRequest,
    DatasetCreateResponse,
    DatasetDetailResponse,
    DatasetListPageResponse,
    DatasetStatusResponse,
    DatasetWorkflowErrorResponse,
)

router = APIRouter(prefix="/datasets", tags=["datasets"])


@router.post("", response_model=DatasetCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_dataset(payload: DatasetCreateRequest, deps: ApiDependencies = Depends(get_deps)) -> DatasetCreateResponse:
    return deps.datasets.submit(payload)


@router.get("", response_model=DatasetListPageResponse)
def list_datasets(deps: ApiDependencies = Depends(get_deps)) -> DatasetListPageResponse:
    return deps.datasets.list_datasets()


@router.get("/{dataset_id}", response_model=DatasetDetailResponse)
def get_dataset(dataset_id: str, deps: ApiDependencies = Depends(get_deps)) -> DatasetDetailResponse:
    detail = deps.datasets.get_detail(dataset_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    return detail


@router.get("/{dataset_id}/status", response_model=DatasetStatusResponse)
def get_dataset_status(dataset_id: str, deps: ApiDependencies = Depends(get_deps)) -> DatasetStatusResponse:
    status_payload = deps.datasets.get_status(dataset_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    return status_payload


@router.post("/{dataset_id}/retry", response_model=DatasetCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def retry_dataset(dataset_id: str, deps: ApiDependencies = Depends(get_deps)) -> DatasetCreateResponse:
    try:
        return deps.datasets.retry_dataset(dataset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}/workflow-errors", response_model=DatasetWorkflowErrorResponse)
def get_dataset_workflow_errors(dataset_id: str, deps: ApiDependencies = Depends(get_deps)) -> DatasetWorkflowErrorResponse:
    error_payload = deps.datasets.get_workflow_errors(dataset_id)
    if error_payload is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")
    return error_payload


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: str, deps: ApiDependencies = Depends(get_deps)) -> None:
    if not deps.datasets.delete_dataset(dataset_id):
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' not found")


@router.get("/{dataset_id}/download")
def download_dataset(dataset_id: str, deps: ApiDependencies = Depends(get_deps)) -> FileResponse:
    path = deps.datasets.get_dataset_parquet_path(dataset_id)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Dataset '{dataset_id}' parquet not found")
    return FileResponse(
        path,
        media_type="application/octet-stream",
        filename=path.name,
    )
