from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, Response
from pydantic import ValidationError

from app.api.deps import ApiDependencies, get_deps
from app.backtests import (
    BacktestConfigUpdateRequest,
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestListItem,
    BacktestListPageResponse,
    BacktestRetryRequest,
    BacktestTradeReplayResponse,
    BacktestStatusResponse,
    BacktestUpdateRequest,
    ClassicBacktestCreateRequest,
    VectorbtBacktestCreateRequest,
    validate_backtest_create_request,
)
from app.backtests.service import (
    ArgoNotConfiguredError,
    ArgoResultsNotSharedError,
    BacktestJobActiveError,
)

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("", response_model=BacktestCreateResponse, status_code=status.HTTP_202_ACCEPTED)
def create_backtest(
    payload: dict[str, Any] = Body(...),
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestCreateResponse:
    try:
        payload = validate_backtest_create_request(payload)
        settings = deps.settings_service.load()
        if isinstance(payload, ClassicBacktestCreateRequest):
            payload = payload.model_copy(
                update={
                    "broker": payload.broker or settings.backtest_defaults.broker,
                    "analyzers": payload.analyzers or settings.backtest_defaults.analyzers,
                    "execution": payload.execution or settings.backtest_defaults.execution,
                }
            )
        return deps.backtest_jobs.submit(payload)
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ArgoNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ArgoResultsNotSharedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("", response_model=BacktestListPageResponse)
def list_backtests(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestListPageResponse:
    return deps.backtest_jobs.list_backtests_page(page=page, page_size=page_size)


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
    report_path = deps.backtest_jobs.resolve_report_file_path(backtest_id)
    if report_path is None:
        raise HTTPException(status_code=404, detail=f"Backtest report '{backtest_id}' not found")
    return FileResponse(
        report_path,
        media_type="application/json",
        filename=f"{backtest_id}.json",
    )


@router.post(
    "/{backtest_id}/retry",
    response_model=BacktestCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_backtest(
    backtest_id: str,
    payload: BacktestRetryRequest | None = None,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestCreateResponse:
    try:
        return deps.backtest_jobs.retry_backtest(backtest_id, payload)
    except BacktestJobActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ArgoNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ArgoResultsNotSharedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{backtest_id}/config")
def get_backtest_config(
    backtest_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> Response:
    yaml_text = deps.backtest_jobs.resolve_config_yaml_text(backtest_id)
    if yaml_text is None:
        raise HTTPException(status_code=404, detail=f"Backtest config '{backtest_id}' not found")
    return Response(
        content=yaml_text,
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'inline; filename="{backtest_id}.yaml"'},
    )


@router.get(
    "/{backtest_id}/runs/{run_id}/trades/{trade_index}/replay-capsule",
    response_model=BacktestTradeReplayResponse,
)
def get_trade_replay_capsule(
    backtest_id: str,
    run_id: str,
    trade_index: int,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestTradeReplayResponse:
    try:
        return deps.backtest_jobs.get_trade_replay(backtest_id, run_id, trade_index)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{backtest_id}/config", response_model=BacktestListItem)
def update_backtest_config(
    backtest_id: str,
    payload: BacktestConfigUpdateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestListItem:
    try:
        return deps.backtest_jobs.update_config(backtest_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_backtest(
    backtest_id: str,
    deps: ApiDependencies = Depends(get_deps),
) -> None:
    if not deps.backtest_jobs.delete(backtest_id):
        raise HTTPException(status_code=404, detail=f"Backtest '{backtest_id}' not found")


@router.patch("/{backtest_id}", response_model=BacktestListItem)
def update_backtest(
    backtest_id: str,
    payload: BacktestUpdateRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestListItem:
    try:
        return deps.backtest_jobs.update_name(backtest_id, payload.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
