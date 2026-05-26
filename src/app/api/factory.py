from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app.api.deps import ApiDependencies
from app.api.routes import register_routes
from app.api_logging import configure_api_logging
from app.backtests import BacktestJobService, BacktestResultRepository
from app.backtests.argo import ArgoWorkflowSubmitter
from app.config.models import DataCacheConfig
from app.data.downloads import DataDownloadJobRepository, DataDownloadJobService
from app.settings import PlatformSettingsService


def create_app(
    cache_config: DataCacheConfig | None = None,
    output_dir: Path | None = None,
    log_file: Path | None = None,
) -> FastAPI:
    logger = configure_api_logging(log_file)
    app = FastAPI(title="Backtest Market Data API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["DELETE", "GET", "PATCH", "POST", "PUT"],
        allow_headers=["*"],
    )
    resolved_cache_config = cache_config or DataCacheConfig(
        directory=os.environ.get("BACKTEST_CACHE_DIR") or DataCacheConfig().directory
    )
    env_results_dir = os.environ.get("BACKTEST_RESULTS_DIR")
    resolved_output_dir = (
        output_dir
        or (Path(env_results_dir) if env_results_dir else None)
        or (Path(tempfile.gettempdir()) / "backtest-api-results")
    ).resolve()
    settings_service = PlatformSettingsService(resolved_output_dir / "settings" / "platform-settings.json")
    data_download_repository = DataDownloadJobRepository(resolved_output_dir)
    app.state.deps = ApiDependencies(
        cache_config=resolved_cache_config,
        output_dir=resolved_output_dir,
        backtest_jobs=BacktestJobService(
            BacktestResultRepository(resolved_output_dir),
            resolved_cache_config,
            settings_service=settings_service,
            argo_submitter=ArgoWorkflowSubmitter(),
        ),
        data_download_jobs=DataDownloadJobService(data_download_repository, resolved_cache_config),
        settings_service=settings_service,
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("%s %s failed", request.method, request.url.path)
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    register_routes(app)
    return app
