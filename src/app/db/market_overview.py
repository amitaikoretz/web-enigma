from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base, json_type


class MarketOverviewSnapshotRow(Base):
    __tablename__ = "market_overview_snapshots"
    __table_args__ = (
        Index("ix_market_overview_snapshots_created_at", "created_at"),
        Index("ix_market_overview_snapshots_status", "status"),
        Index("ix_market_overview_snapshots_as_of", "as_of"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    argo_namespace: Mapped[str | None] = mapped_column(String(128), nullable=True)
    argo_workflow_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    as_of: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    top_regime: Mapped[str | None] = mapped_column(String(128), nullable=True)
    probabilities_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    fragility: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    contradiction_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    market_indicators_json: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    pillar_scores_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    developments_json: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    freshness_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    watch_next_json: Mapped[list] = mapped_column(json_type, nullable=False, default=list)
    methodology_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    evidence_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    params_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
