from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from starlette.requests import Request

from app.backtests import BacktestJobService
from app.config.models import DataCacheConfig
from app.settings import PlatformSettingsService


@dataclass(frozen=True)
class ApiDependencies:
    cache_config: DataCacheConfig
    output_dir: Path
    backtest_jobs: BacktestJobService
    settings_service: PlatformSettingsService


def get_deps(request: Request) -> ApiDependencies:
    return request.app.state.deps
