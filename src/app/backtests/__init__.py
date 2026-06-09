from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.backtests.models import (
        BacktestArgoLaunchRequest,
        BacktestArgoLaunchResponse,
        BacktestConfigUpdateRequest,
        BacktestCreateRequest,
        BacktestCreateResponse,
        BacktestDetailResponse,
        BacktestListItem,
        BacktestListPageResponse,
        BacktestRetryRequest,
        BacktestSelectionSummary,
        BacktestTradeReplayCapsule,
        BacktestTradeReplayResponse,
        BacktestStatusResponse,
        BacktestUpdateRequest,
    )
    from app.backtests.persistence import BacktestArtifactPaths, SqlAlchemyBacktestJobRepository
    from app.backtests.service import (
        BacktestArtifactStore,
        BacktestJobService,
        BacktestResultRepository,
        build_backtest_config,
        build_backtest_config_raw,
    )

__all__ = [
    "BacktestArgoLaunchRequest",
    "BacktestArgoLaunchResponse",
    "BacktestArtifactPaths",
    "BacktestArtifactStore",
    "BacktestConfigUpdateRequest",
    "BacktestCreateRequest",
    "BacktestCreateResponse",
    "BacktestDetailResponse",
    "BacktestJobService",
    "BacktestListItem",
    "BacktestListPageResponse",
    "BacktestResultRepository",
    "BacktestRetryRequest",
    "BacktestSelectionSummary",
    "BacktestTradeReplayCapsule",
    "BacktestTradeReplayResponse",
    "BacktestStatusResponse",
    "BacktestUpdateRequest",
    "SqlAlchemyBacktestJobRepository",
    "build_backtest_config",
    "build_backtest_config_raw",
]


def __getattr__(name: str) -> Any:
    if name in {
        "BacktestArgoLaunchRequest",
        "BacktestArgoLaunchResponse",
        "BacktestArtifactPaths",
        "BacktestArtifactStore",
        "BacktestConfigUpdateRequest",
        "BacktestCreateRequest",
        "BacktestCreateResponse",
        "BacktestDetailResponse",
        "BacktestJobService",
        "BacktestListItem",
        "BacktestListPageResponse",
        "BacktestResultRepository",
        "BacktestRetryRequest",
        "BacktestSelectionSummary",
        "BacktestTradeReplayCapsule",
        "BacktestTradeReplayResponse",
        "BacktestStatusResponse",
        "BacktestUpdateRequest",
        "SqlAlchemyBacktestJobRepository",
        "build_backtest_config",
        "build_backtest_config_raw",
    }:
        from app.backtests.models import (
            BacktestArgoLaunchRequest,
            BacktestArgoLaunchResponse,
            BacktestConfigUpdateRequest,
            BacktestCreateRequest,
            BacktestCreateResponse,
            BacktestDetailResponse,
            BacktestListItem,
            BacktestListPageResponse,
            BacktestRetryRequest,
            BacktestSelectionSummary,
            BacktestTradeReplayCapsule,
            BacktestTradeReplayResponse,
            BacktestStatusResponse,
            BacktestUpdateRequest,
        )
        from app.backtests.persistence import BacktestArtifactPaths, SqlAlchemyBacktestJobRepository
        from app.backtests.service import (
            BacktestArtifactStore,
            BacktestJobService,
            BacktestResultRepository,
            build_backtest_config,
            build_backtest_config_raw,
        )

        return {
            "BacktestArgoLaunchRequest": BacktestArgoLaunchRequest,
            "BacktestArgoLaunchResponse": BacktestArgoLaunchResponse,
            "BacktestArtifactPaths": BacktestArtifactPaths,
            "BacktestArtifactStore": BacktestArtifactStore,
            "BacktestConfigUpdateRequest": BacktestConfigUpdateRequest,
            "BacktestCreateRequest": BacktestCreateRequest,
            "BacktestCreateResponse": BacktestCreateResponse,
            "BacktestDetailResponse": BacktestDetailResponse,
            "BacktestJobService": BacktestJobService,
            "BacktestListItem": BacktestListItem,
            "BacktestListPageResponse": BacktestListPageResponse,
            "BacktestResultRepository": BacktestResultRepository,
            "BacktestRetryRequest": BacktestRetryRequest,
            "BacktestSelectionSummary": BacktestSelectionSummary,
            "BacktestTradeReplayCapsule": BacktestTradeReplayCapsule,
            "BacktestTradeReplayResponse": BacktestTradeReplayResponse,
            "BacktestStatusResponse": BacktestStatusResponse,
            "BacktestUpdateRequest": BacktestUpdateRequest,
            "SqlAlchemyBacktestJobRepository": SqlAlchemyBacktestJobRepository,
            "build_backtest_config": build_backtest_config,
            "build_backtest_config_raw": build_backtest_config_raw,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
