from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pathlib import Path

from starlette.responses import FileResponse

from app.api.deps import ApiDependencies, get_deps
from app.scans.models import ScanCreateRequest, ScanListResponse, ScanStatusResponse, ScanType
from app.scans.params import params_model_for_scan_type

router = APIRouter(prefix="/scanners", tags=["scanners"])


@router.post("/{scan_type}/runs", response_model=ScanStatusResponse)
def create_scan_run(
    scan_type: ScanType,
    request: ScanCreateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> ScanStatusResponse:
    return deps.scan_jobs.create_scan(scan_type, request)


@router.get("/{scan_type}/runs", response_model=ScanListResponse)
def list_scan_runs(
    scan_type: ScanType,
    deps: ApiDependencies = Depends(get_deps),
) -> ScanListResponse:
    items = deps.scan_jobs.list_scans(scan_type, limit=10)
    return ScanListResponse(items=items)


@router.get("/{scan_type}/runs/{scan_id}", response_model=ScanStatusResponse)
def get_scan_run(
    scan_type: ScanType,
    scan_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> ScanStatusResponse:
    item = deps.scan_jobs.get_scan(scan_type, scan_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Scan run not found")
    return item


@router.get("/{scan_type}/runs/{scan_id}/results")
def download_scan_results(
    scan_type: ScanType,
    scan_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> FileResponse:
    item = deps.scan_jobs.get_scan(scan_type, scan_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Scan run not found")
    if not item.results_json_path:
        raise HTTPException(status_code=404, detail="Results not available")
    file_path = Path(item.results_json_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Results file not found")
    return FileResponse(path=str(file_path), media_type="application/json", filename="results.json")


@router.get("/{scan_type}/params")
def get_scan_params_schema(scan_type: ScanType) -> dict:
    """
    Used by the web UI to render themed parameter widgets instead of raw JSON.
    """
    model = params_model_for_scan_type(scan_type)
    return {
        "scan_type": scan_type,
        "defaults": model().model_dump(),
        "schema": model.model_json_schema(),
    }
