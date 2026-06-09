from __future__ import annotations

from fastapi import APIRouter

from app.api.helpers.strategies import build_strategy_parameters
from app.api.schemas.strategies import StrategyMetadataResponse
from app.strategies.exit_rules import list_exit_rules
from app.strategies.triggers import list_triggers

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyMetadataResponse])
def get_strategies() -> list[StrategyMetadataResponse]:
    return [
        StrategyMetadataResponse(
            name=spec.name,
            description=spec.description,
            documentation=spec.documentation,
            parameters=build_strategy_parameters(spec.params_model),
        )
        for spec in list_triggers()
    ]


@router.get("/exit-rules", response_model=list[StrategyMetadataResponse])
def get_exit_rules() -> list[StrategyMetadataResponse]:
    return [
        StrategyMetadataResponse(
            name=spec.name,
            description=spec.description,
            documentation=getattr(spec, "documentation", spec.description),
            parameters=build_strategy_parameters(spec.params_model),
        )
        for spec in list_exit_rules()
    ]
