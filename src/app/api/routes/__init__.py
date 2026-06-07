from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import (
    argo,
    backtests_argo,
    backtests_jobs,
    backtests_run,
    health,
    live_runtime,
    market_data,
    market_data_downloads,
    scans,
    server,
    settings,
    symbol_universes,
    daily_index_forecast_models,
    risk_models,
    return_forecast_models,
    strategies,
    trading_contracts,
)


def register_routes(app: FastAPI) -> None:
    app.include_router(argo.router)
    app.include_router(health.router)
    app.include_router(server.router)
    app.include_router(strategies.router)
    app.include_router(settings.router)
    app.include_router(backtests_argo.router)
    app.include_router(backtests_jobs.router)
    app.include_router(backtests_run.router)
    app.include_router(market_data.router)
    app.include_router(market_data_downloads.router)
    app.include_router(scans.router)
    app.include_router(risk_models.router)
    app.include_router(return_forecast_models.router)
    app.include_router(daily_index_forecast_models.router)
    app.include_router(trading_contracts.router)
    app.include_router(live_runtime.router)
    app.include_router(symbol_universes.router)
