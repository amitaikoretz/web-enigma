from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


MarketOverviewStatus = Literal["pending", "running", "completed", "failed"]


class MarketOverviewIndicatorExplanation(BaseModel):
    summary: str
    inputs: list[str] = Field(default_factory=list)
    calculation_steps: list[str] = Field(default_factory=list)
    interpretation: str
    freshness: str | None = None
    caveats: list[str] = Field(default_factory=list)


class MarketOverviewIndicator(BaseModel):

    key: str
    label: str
    value: str
    change: str | None = None
    tone: Literal["positive", "negative", "neutral", "warning", "info"] = "neutral"
    category: str | None = None
    note: str | None = None
    explanation: MarketOverviewIndicatorExplanation | None = None


class MarketOverviewMethodology(BaseModel):
    summary: str
    inputs: list[str] = Field(default_factory=list)
    scoring: list[str] = Field(default_factory=list)
    freshness: str | None = None
    caveats: list[str] = Field(default_factory=list)


class MarketOverviewCreateRequest(BaseModel):
    name: str | None = None
    as_of: datetime | None = None


class MarketOverviewLaunchRequest(BaseModel):
    name: str | None = None
    as_of: datetime | None = None


class MarketOverviewSnapshot(BaseModel):
    snapshot_id: str
    name: str | None = None
    status: MarketOverviewStatus
    argo_namespace: str | None = None
    argo_workflow_name: str | None = None
    as_of: datetime | None = None
    top_regime: str | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    confidence: float = 0.0
    fragility: float = 0.0
    contradiction_score: float = 0.0
    market_indicators: list[MarketOverviewIndicator] = Field(default_factory=list)
    pillar_scores: dict[str, Any] = Field(default_factory=dict)
    developments: list[dict[str, Any]] = Field(default_factory=list)
    freshness: dict[str, Any] = Field(default_factory=dict)
    summary_text: str | None = None
    watch_next: list[str] = Field(default_factory=list)
    methodology: MarketOverviewMethodology | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class MarketOverviewListResponse(BaseModel):
    items: list[MarketOverviewSnapshot]


class MarketOverviewDetailResponse(MarketOverviewSnapshot):
    pass


class MarketOverviewLaunchResponse(BaseModel):
    snapshot_id: str
    status: MarketOverviewStatus
    argo_namespace: str
    argo_workflow_name: str
