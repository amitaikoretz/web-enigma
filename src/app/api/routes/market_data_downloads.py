from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import ApiDependencies, get_deps
from app.data.downloads import (
    DataDownloadCreateRequest,
    DataDownloadCreateResponse,
    DataDownloadDetailResponse,
    DataDownloadStatusResponse,
    InvalidOutputFolderError,
)

router = APIRouter(prefix="/market-data/downloads", tags=["market-data"])


@router.post("", response_model=DataDownloadCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_data_download(
    payload: DataDownloadCreateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> DataDownloadCreateResponse:
    try:
        return deps.data_download_jobs.submit(payload)
    except InvalidOutputFolderError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[DataDownloadStatusResponse])
def list_data_downloads(
    deps: ApiDependencies = Depends(get_deps),
) -> list[DataDownloadStatusResponse]:
    return deps.data_download_jobs.list_jobs()


@router.get("/{job_id}", response_model=DataDownloadDetailResponse)
def get_data_download(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> DataDownloadDetailResponse:
    detail = deps.data_download_jobs.get_detail(job_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Data download job '{job_id}' not found")
    return detail


@router.get("/{job_id}/status", response_model=DataDownloadStatusResponse)
def get_data_download_status(
    job_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> DataDownloadStatusResponse:
    status_payload = deps.data_download_jobs.get_status(job_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail=f"Data download job '{job_id}' not found")
    return status_payload
