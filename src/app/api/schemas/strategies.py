from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class StrategyParameterMetadata(BaseModel):
    type: str
    default: Any | None = None
    required: bool
    minimum: float | int | None = None
    maximum: float | int | None = None
    exclusiveMinimum: float | int | None = None
    exclusiveMaximum: float | int | None = None
    minLength: int | None = None
    maxLength: int | None = None
    pattern: str | None = None


class StrategyMetadataResponse(BaseModel):
    name: str
    description: str
    parameters: dict[str, StrategyParameterMetadata]
