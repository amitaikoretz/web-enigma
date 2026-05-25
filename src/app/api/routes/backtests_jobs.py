from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse, Response

from app.api.deps import ApiDependencies, get_deps
from app.backtests import (
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestStatusResponse,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", response_model=BacktestCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_backtest(
    payload: BacktestCreateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestCreateResponse:
    settings = deps.settings_service.load()
    payload = payload.model_copy(
        update={
            "broker": payload.broker or settings.backtest_defaults.broker,
            "analyzers": payload.analyzers or settings.backtest_defaults.analyzers,
            "execution": payload.execution or settings.backtest_defaults.execution,
        }
    )
    return deps.backtest_jobs.submit(payload)


@router.get("", response_model=list[BacktestListItem])
def list_backtests(deps: ApiDependencies = Depends(get_deps)) -> list[BacktestListItem]:
    return deps.backtest_jobs.list_backtests()


@router.get("/{backtest_id}", response_model=BacktestDetailResponse)
def get_backtest(
    backtest_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestDetailResponse:
    detail = deps.backtest_jobs.get_detail(backtest_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Backtest '{backtest_id}' not found")
    return detail


@router.get("/{backtest_id}/status", response_model=BacktestStatusResponse)
def get_backtest_status(
    backtest_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestStatusResponse:
    status_payload = deps.backtest_jobs.get_status(backtest_id)
    if status_payload is None:
        raise HTTPException(status_code=404, detail=f"Backtest '{backtest_id}' not found")
    return status_payload


@router.get("/{backtest_id}/report")
def get_backtest_report(
    backtest_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> FileResponse:
    report_path = deps.backtest_jobs.repository.report_path(backtest_id)
    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Backtest report '{backtest_id}' not found")
    return FileResponse(
        report_path,
        media_type="application/json",
        filename=f"{backtest_id}.json",
    )


@router.get("/{backtest_id}/config")
def get_backtest_config(
    backtest_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> Response:
    yaml_text = deps.backtest_jobs.repository.resolve_config_yaml(backtest_id)
    if yaml_text is None:
        raise HTTPException(status_code=404, detail=f"Backtest config '{backtest_id}' not found")
    return Response(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'inline; filename="{backtest_id}.yaml"'},
    )


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backtest(
    backtest_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> None:
    if not deps.backtest_jobs.delete(backtest_id):
        raise HTTPException(status_code=404, detail=f"Backtest '{backtest_id}' not found")
