from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.market_overview import MarketOverviewSnapshotRow
from app.market_overview.models import MarketOverviewSnapshot


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MarketOverviewArtifactPaths:
    snapshot_json_path: str | None = None


class SqlAlchemyMarketOverviewRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def upsert(self, snapshot: MarketOverviewSnapshot) -> None:
        with self._session_factory() as session:
            row = session.get(MarketOverviewSnapshotRow, snapshot.snapshot_id)
            payload = snapshot.model_dump(mode="json")
            if row is None:
                row = MarketOverviewSnapshotRow(snapshot_id=snapshot.snapshot_id)
                session.add(row)
            row.name = payload["name"]
            row.status = payload["status"]
            row.argo_namespace = payload["argo_namespace"]
            row.argo_workflow_name = payload["argo_workflow_name"]
            row.as_of = snapshot.as_of
            row.top_regime = payload["top_regime"]
            row.probabilities_json = payload["probabilities"]
            row.confidence = payload["confidence"]
            row.fragility = payload["fragility"]
            row.contradiction_score = payload["contradiction_score"]
            row.pillar_scores_json = payload["pillar_scores"]
            row.developments_json = payload["developments"]
            row.freshness_json = payload["freshness"]
            row.summary_text = payload["summary_text"]
            row.evidence_json = payload["evidence"]
            row.params_json = payload["params"]
            row.error_message = payload["error_message"]
            row.updated_at = _utc_now()
            if row.created_at is None:
                row.created_at = row.updated_at
            session.commit()

    def get_latest(self) -> MarketOverviewSnapshot | None:
        with self._session_factory() as session:
            row = session.scalars(
                select(MarketOverviewSnapshotRow).order_by(MarketOverviewSnapshotRow.created_at.desc())
            ).first()
            if row is None:
                return None
            return self._row_to_snapshot(row)

    def list_recent(self, *, limit: int = 100) -> list[MarketOverviewSnapshot]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(MarketOverviewSnapshotRow).order_by(MarketOverviewSnapshotRow.created_at.desc()).limit(limit)
            ).all()
            return [self._row_to_snapshot(row) for row in rows]

    def get(self, snapshot_id: str) -> MarketOverviewSnapshot | None:
        with self._session_factory() as session:
            row = session.get(MarketOverviewSnapshotRow, snapshot_id)
            return self._row_to_snapshot(row) if row is not None else None

    def _row_to_snapshot(self, row: MarketOverviewSnapshotRow) -> MarketOverviewSnapshot:
        return MarketOverviewSnapshot(
            snapshot_id=row.snapshot_id,
            name=row.name,
            status=row.status,  # type: ignore[arg-type]
            argo_namespace=row.argo_namespace,
            argo_workflow_name=row.argo_workflow_name,
            as_of=row.as_of,
            top_regime=row.top_regime,
            probabilities=row.probabilities_json or {},
            confidence=float(row.confidence or 0.0),
            fragility=float(row.fragility or 0.0),
            contradiction_score=float(row.contradiction_score or 0.0),
            pillar_scores=row.pillar_scores_json or {},
            developments=list(row.developments_json or []),
            freshness=row.freshness_json or {},
            summary_text=row.summary_text,
            evidence=row.evidence_json or {},
            params=row.params_json or {},
            error_message=row.error_message,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
