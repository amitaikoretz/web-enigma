from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError

from app.api.deps import ApiDependencies, get_deps
from app.api.errors import http_error_from_loader_error
from app.api.helpers.market_data import frame_to_rows
from app.api.schemas.market_data import BarsQueryParams, MarketDataResponse
from app.config.models import AlpacaDataSource
from app.data.loaders import build_alpaca_data_feed_with_cache

router = APIRouter(prefix="/symbols", tags=["market-data"])


@router.get("/{symbol}/bars", response_model=MarketDataResponse)
def get_symbol_bars(
    symbol: str,
    start_date: date = Query(...),
    stop_date: date = Query(...),
    resolution: str = Query(...),
    feed: Literal["iex", "sip", "otc"] = Query("iex"),
    force_refresh: bool = Query(False),
    deps: ApiDependencies = Depends(get_deps),
) -> MarketDataResponse:
    try:
        params = BarsQueryParams(
            start_date=start_date,
            stop_date=stop_date,
            resolution=resolution,
            feed=feed,
            force_refresh=force_refresh,
        )
    except ValidationError as exc:
        errors = [error["msg"] for error in exc.errors()]
        raise HTTPException(status_code=422, detail=errors) from exc
    normalized_symbol = symbol.upper()
    data_source = AlpacaDataSource(
        type="alpaca",
        symbol=normalized_symbol,
        interval=params.resolution,
        feed=params.feed,
    )

    try:
        frame, cache_status = build_alpaca_data_feed_with_cache(
            data_source,
            params.start_date,
            params.stop_date,
            deps.cache_config,
            force_refresh=params.force_refresh,
        )
    except RuntimeError as exc:
        raise http_error_from_loader_error(exc) from exc

    return MarketDataResponse(
        symbol=normalized_symbol,
        provider="alpaca",
        resolution=params.resolution,
        start_date=params.start_date,
        stop_date=params.stop_date,
        cache_status=cache_status,
        rows=frame_to_rows(frame),
    )
