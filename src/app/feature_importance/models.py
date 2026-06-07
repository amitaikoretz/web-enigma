from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class FeatureImportanceRow(BaseModel):
    feature: str
    importance: float
    signed_importance: float | None = None


class FeatureImportanceTarget(BaseModel):
    target_key: str
    rows: list[FeatureImportanceRow] = Field(default_factory=list)


class FeatureImportanceArtifact(BaseModel):
    generated_at: datetime
    source: str | None = None
    targets: list[FeatureImportanceTarget] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

