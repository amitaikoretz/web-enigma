from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from starlette.requests import Request

from app.backtests import BacktestJobService
from app.config.models import DataCacheConfig
from app.data.downloads import DataDownloadJobRepository, DataDownloadJobService
from app.scans.service import ScanJobService
from app.settings import PlatformSettingsService
from app.risk.persistence import SqlAlchemyRiskModelRepository
from app.risk.service import RiskModelService


@dataclass(frozen=True)
class ApiDependencies:
    cache_config: DataCacheConfig
    output_dir: Path
    backtest_jobs: BacktestJobService
    data_download_jobs: DataDownloadJobService
    scan_jobs: ScanJobService
    settings_service: PlatformSettingsService
    risk_models: RiskModelService
    risk_models_repo: SqlAlchemyRiskModelRepository


def get_deps(request: Request) -> ApiDependencies:
    return request.app.state.deps
