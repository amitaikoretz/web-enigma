from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import ApiDependencies, get_deps
from app.market_overview.models import (
    MarketOverviewCreateRequest,
    MarketOverviewDetailResponse,
    MarketOverviewLaunchResponse,
    MarketOverviewLaunchRequest,
    MarketOverviewListResponse,
)

router = APIRouter(prefix="/market-overview", tags=["market-overview"])


@router.get("", response_model=MarketOverviewListResponse)
def list_market_overview(deps: ApiDependencies = Depends(get_deps)) -> MarketOverviewListResponse:
    return MarketOverviewListResponse(items=deps.market_overview.list_recent(limit=200))


@router.get("/latest", response_model=MarketOverviewDetailResponse)
def get_latest_market_overview(deps: ApiDependencies = Depends(get_deps)) -> MarketOverviewDetailResponse:
    snapshot = deps.market_overview.get_latest()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No market overview snapshot found")
    return MarketOverviewDetailResponse.model_validate(snapshot.model_dump())


@router.get("/{snapshot_id}", response_model=MarketOverviewDetailResponse)
def get_market_overview(snapshot_id: str, deps: ApiDependencies = Depends(get_deps)) -> MarketOverviewDetailResponse:
    snapshot = deps.market_overview.get(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Market overview snapshot not found")
    return MarketOverviewDetailResponse.model_validate(snapshot.model_dump())


@router.post("", response_model=MarketOverviewLaunchResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_market_overview(
    payload: MarketOverviewLaunchRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> MarketOverviewLaunchResponse:
    try:
        result = deps.market_overview.create_and_submit_argo(MarketOverviewCreateRequest.model_validate(payload.model_dump()))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return MarketOverviewLaunchResponse(
        snapshot_id=result.snapshot_id,
        status=result.status,  # type: ignore[arg-type]
        argo_namespace=result.argo_namespace,
        argo_workflow_name=result.argo_workflow_name,
    )
