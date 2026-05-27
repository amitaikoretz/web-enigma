from __future__ import annotations

import json

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.api.deps import ApiDependencies, get_deps
from app.api.errors import http_error_from_loader_error, validation_error
from app.api.helpers.backtests import (
    build_backtest_output_path,
    build_single_day_config_raw,
    parse_inline_backtest_config,
)
from app.api.helpers.market_data import frame_to_rows
from app.api.schemas.backtests import (
    BacktestRunRequest,
    BacktestRunResponse,
    SingleDayBacktestRequest,
    SingleDayBacktestResponse,
    SingleDayBacktestResult,
)
from app.config.models import AlpacaDataSource, BacktestConfig
from app.data.loaders import build_alpaca_data_feed_with_cache
from app.engine.runner import run_backtests
from app.backtests.artifacts import persist_backtest_report
from app.output.models import RunError

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.post("/run", response_model=BacktestRunResponse)
def run_backtest(
    payload: BacktestRunRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> BacktestRunResponse:
    try:
        config_raw = parse_inline_backtest_config(payload)
        config = BacktestConfig.model_validate(config_raw)
    except (ValidationError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise validation_error(exc) from exc

    try:
        report = run_backtests(config, config_raw)
        output_path = build_backtest_output_path(deps.output_dir)
        persist_backtest_report(report, output_path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to execute backtest: {exc}") from exc

    return BacktestRunResponse(
        output_path=str(output_path),
        status=report.status,
        total_runs=report.total_runs,
        successful_runs=report.successful_runs,
        failed_runs=report.failed_runs,
    )


@router.post("/single-day", response_model=SingleDayBacktestResponse)
def run_single_day_backtest(
    payload: SingleDayBacktestRequest,
    deps: ApiDependencies = Depends(get_deps),
) -> SingleDayBacktestResponse:
    try:
        config_raw = build_single_day_config_raw(payload)
        config = BacktestConfig.model_validate(config_raw)
    except (ValidationError, ValueError) as exc:
        raise validation_error(exc) from exc

    data_source = AlpacaDataSource(
        type="alpaca",
        symbol=payload.symbol,
        interval=payload.resolution,
        feed=payload.feed,
    )
    try:
        frame, cache_status = build_alpaca_data_feed_with_cache(
            data_source,
            payload.date,
            payload.date,
            deps.cache_config,
            force_refresh=False,
        )
    except RuntimeError as exc:
        raise http_error_from_loader_error(exc) from exc

    try:
        report = run_backtests(config, config_raw)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Failed to execute backtest: {exc}") from exc

    result = report.results[0] if report.results else None
    if result is None or result.status == "failed":
        backtest = SingleDayBacktestResult(
            status="failed",
            summary=result.summary if result else None,
            orders=result.orders if result else [],
            trades=result.trades if result else [],
            error=result.error if result else RunError(type="BacktestError", message="Backtest produced no results"),
        )
    else:
        backtest = SingleDayBacktestResult(
            status="success",
            summary=result.summary,
            orders=result.orders,
            trades=result.trades,
            error=None,
        )

    return SingleDayBacktestResponse(
        symbol=payload.symbol,
        date=payload.date,
        resolution=payload.resolution,
        cache_status=cache_status,
        bars=frame_to_rows(frame),
        backtest=backtest,
    )
