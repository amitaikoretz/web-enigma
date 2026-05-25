from __future__ import annotations

from fastapi import APIRouter

from app.api.helpers.strategies import build_strategy_parameters
from app.api.schemas.strategies import StrategyMetadataResponse
from app.strategies.registry import list_strategies

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyMetadataResponse])
def get_strategies() -> list[StrategyMetadataResponse]:
    return [
        StrategyMetadataResponse(
            name=spec.name,
            description=spec.description,
            parameters=build_strategy_parameters(spec.params_model),
        )
        for spec in list_strategies()
    ]
