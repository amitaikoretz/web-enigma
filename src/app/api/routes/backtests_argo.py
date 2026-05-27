from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError

from app.api.deps import ApiDependencies, get_deps
from app.backtests.models import BacktestArgoLaunchRequest, BacktestArgoLaunchResponse, ArgoSplitBy
from app.backtests.service import ArgoNotConfiguredError, ArgoResultsNotSharedError, BacktestAlreadyExistsError

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("/argo", response_model=BacktestArgoLaunchResponse, status_code=status.HTTP_202_ACCEPTED)
def launch_argo_backtest(
    payload: BacktestArgoLaunchRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestArgoLaunchResponse:
    try:
        return deps.backtest_jobs.submit_argo(payload)
    except ArgoNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ArgoResultsNotSharedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except BacktestAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/{backtest_id}/argo",
    response_model=BacktestArgoLaunchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def relaunch_argo_backtest(
    backtest_id: str,
    split_by: ArgoSplitBy | None = Query(default=None),
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestArgoLaunchResponse:
    try:
        return deps.backtest_jobs.relaunch_argo(backtest_id, split_by=split_by)
    except ArgoNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ArgoResultsNotSharedError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
