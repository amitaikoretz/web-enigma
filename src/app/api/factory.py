from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request

from app.api.deps import ApiDependencies
from app.api.errors import register_exception_handlers
from app.api.routes import register_routes
from app.api_logging import configure_api_logging
from sqlalchemy.orm import Session, sessionmaker

from app.backtests import BacktestArtifactStore, BacktestJobService
from app.backtests.argo import ArgoWorkflowSubmitter
from app.backtests.persistence import SqlAlchemyBacktestJobRepository
from app.config.models import DataCacheConfig
from app.data.downloads import DataDownloadJobRepository, DataDownloadJobService
from app.db.session import get_session_factory
from app.scans.argo import ScanArgoSubmitter
from app.scans.repository import ScanJobRepository
from app.scans.service import ScanJobService
from app.settings import PlatformSettingsService
from app.risk.persistence import SqlAlchemyRiskModelRepository
from app.risk.service import RiskModelService
from app.daily_index_forecast.persistence import SqlAlchemyDailyIndexForecastRepository
from app.daily_index_forecast.service import DailyIndexForecastService


def create_app(
    cache_config: DataCacheConfig | None = None,
    output_dir: Path | None = None,
    log_file: Path | None = None,
    session_factory: sessionmaker[Session] | None = None,
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

    def _is_writable_dir(candidate: Path) -> bool:
        try:
            if candidate.exists():
                if not candidate.is_dir():
                    return False
                return os.access(candidate, os.W_OK | os.X_OK)
            parent = candidate.parent
            if not parent.exists() or not parent.is_dir():
                return False
            return os.access(parent, os.W_OK | os.X_OK)
        except OSError:
            return False

    env_results_dir = os.environ.get("BACKTEST_RESULTS_DIR")
    default_pvc_results_dir = Path("/data/backtest-results")
    tmp_results_dir = Path(tempfile.gettempdir()) / "backtest-api-results"

    resolved_output_dir_candidate = (
        output_dir
        or (Path(env_results_dir) if env_results_dir else None)
        or (default_pvc_results_dir if _is_writable_dir(default_pvc_results_dir) else None)
        or tmp_results_dir
    )
    resolved_output_dir = resolved_output_dir_candidate.resolve()
    if resolved_output_dir_candidate != tmp_results_dir and not _is_writable_dir(resolved_output_dir):
        logger.warning(
            "BACKTEST_RESULTS_DIR=%s is not writable; falling back to %s",
            str(resolved_output_dir_candidate),
            str(tmp_results_dir),
        )
        resolved_output_dir = tmp_results_dir.resolve()

    settings_service = PlatformSettingsService(resolved_output_dir / "settings" / "platform-settings.json")
    data_download_repository = DataDownloadJobRepository(resolved_output_dir)
    scan_repository = ScanJobRepository(resolved_output_dir)
    resolved_session_factory = session_factory or get_session_factory()
    backtest_repo = SqlAlchemyBacktestJobRepository(resolved_session_factory)
    risk_repo = SqlAlchemyRiskModelRepository(resolved_session_factory, family="risk")
    return_forecast_repo = SqlAlchemyRiskModelRepository(resolved_session_factory, family="return_forecast")
    daily_index_repo = SqlAlchemyDailyIndexForecastRepository(resolved_session_factory, family="daily_index_forecast")
    app.state.deps = ApiDependencies(
        cache_config=resolved_cache_config,
        output_dir=resolved_output_dir,
        backtest_jobs=BacktestJobService(
            BacktestArtifactStore(resolved_output_dir),
            backtest_repo,
            resolved_cache_config,
            settings_service=settings_service,
            argo_submitter=ArgoWorkflowSubmitter(),
        ),
        data_download_jobs=DataDownloadJobService(data_download_repository, resolved_cache_config),
        scan_jobs=ScanJobService(
            scan_repository,
            argo_submitter=ScanArgoSubmitter(),
            output_dir=resolved_output_dir,
        ),
        settings_service=settings_service,
        risk_models=RiskModelService(
            session_factory=resolved_session_factory,
            backtest_repo=backtest_repo,
            risk_repo=risk_repo,
            argo_submitter=ArgoWorkflowSubmitter(),
            family="risk",
            family_slug="risk-models",
            family_label="Risk model",
        ),
        risk_models_repo=risk_repo,
        return_forecast_models=RiskModelService(
            session_factory=resolved_session_factory,
            backtest_repo=backtest_repo,
            risk_repo=return_forecast_repo,
            argo_submitter=ArgoWorkflowSubmitter(),
            family="return_forecast",
            family_slug="return-forecast-models",
            family_label="Return forecast model",
        ),
        return_forecast_models_repo=return_forecast_repo,
        daily_index_forecast_models=DailyIndexForecastService(
            session_factory=resolved_session_factory,
            repo=daily_index_repo,
            argo_submitter=ArgoWorkflowSubmitter(),
            family="daily_index_forecast",
            family_slug="daily-index-forecast-models",
            family_label="Daily Index Forecast",
        ),
        daily_index_forecast_models_repo=daily_index_repo,
    )

    register_exception_handlers(app, logger)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
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
