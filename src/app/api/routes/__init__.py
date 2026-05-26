from __future__ import annotations

from fastapi import FastAPI

from app.api.routes import (
    backtests_argo,
    backtests_jobs,
    backtests_run,
    health,
    live_runtime,
    market_data,
    market_data_downloads,
    server,
    settings,
    strategies,
    trading_contracts,
)


def register_routes(app: FastAPI) -> None:
    app.include_router(health.router)
    app.include_router(server.router)
    app.include_router(strategies.router)
    app.include_router(settings.router)
    app.include_router(backtests_argo.router)
    app.include_router(backtests_jobs.router)
    app.include_router(backtests_run.router)
    app.include_router(market_data.router)
    app.include_router(market_data_downloads.router)
    app.include_router(trading_contracts.router)
    app.include_router(live_runtime.router)
