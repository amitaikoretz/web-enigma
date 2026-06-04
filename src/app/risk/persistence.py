from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.backtests.models import BacktestSelectionSummary
from app.db.models import RiskModelGroup, RiskModelSource, RiskModelTarget
from app.db.models import BacktestJob


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class RiskModelListItem:
    group_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    argo_namespace: str | None
    argo_workflow_name: str | None
    backtest_ids: list[str]
    targets: list[str]
    targets_total: int
    targets_done: int
    summary_metrics: dict[str, Any] | None
    artifact_dir: str
    training_start_date: date | None
    training_end_date: date | None


@dataclass(frozen=True)
class RiskModelTargetRow:
    id: int
    group_id: str
    target_key: str
    task_type: str
    status: str
    model_artifact_path: str | None
    metrics: dict[str, Any] | None
    dataset_manifest_path: str | None
    feature_columns: list[str] | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class RiskModelDetail:
    group_id: str
    created_at: datetime
    updated_at: datetime
    status: str
    argo_namespace: str | None
    argo_workflow_name: str | None
    params: dict[str, Any]
    artifact_dir: str
    summary_metrics: dict[str, Any] | None
    sources: list[dict[str, Any]]
    targets: list[RiskModelTargetRow]
    training_start_date: date | None
    training_end_date: date | None


class SqlAlchemyRiskModelRepository:
    def __init__(self, session_factory: sessionmaker[Session], *, family: str = "risk"):
        self._session_factory = session_factory
        self._family = family

    def _training_date_range(
        self,
        session: Session,
        backtest_ids: list[str],
    ) -> tuple[date | None, date | None]:
        if not backtest_ids:
            return None, None

        rows = session.scalars(select(BacktestJob).where(BacktestJob.id.in_(backtest_ids))).all()
        start_date: date | None = None
        end_date: date | None = None
        for row in rows:
            selection = row.selection
            if not selection:
                continue
            try:
                parsed = BacktestSelectionSummary.model_validate(selection)
            except Exception:  # noqa: BLE001
                continue
            if start_date is None or parsed.start_date < start_date:
                start_date = parsed.start_date
            if end_date is None or parsed.end_date > end_date:
                end_date = parsed.end_date
        return start_date, end_date

    def create_group(
        self,
        *,
        group_id: str,
        status: str,
        params: dict[str, Any],
        artifact_dir: str,
        backtest_ids: list[str],
        source_report_paths: dict[str, str | None] | None = None,
        argo_namespace: str | None = None,
        argo_workflow_name: str | None = None,
    ) -> None:
        now = _utc_now()
        with self._session_factory() as session:
            row = RiskModelGroup(
                id=group_id,
                family=self._family,
                status=status,
                argo_namespace=argo_namespace,
                argo_workflow_name=argo_workflow_name,
                params_json=params,
                artifact_dir=artifact_dir,
                summary_metrics_json=None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            for backtest_id in backtest_ids:
                session.add(
                    RiskModelSource(
                        group_id=group_id,
                        backtest_id=backtest_id,
                        source_report_path=(source_report_paths or {}).get(backtest_id),
                    )
                )
            session.commit()

    def update_group_workflow(self, group_id: str, *, argo_namespace: str, argo_workflow_name: str) -> None:
        with self._session_factory() as session:
            row = session.get(RiskModelGroup, group_id)
            if row is None or row.family != self._family:
                raise KeyError(f"Risk model group '{group_id}' not found")
            row.argo_namespace = argo_namespace
            row.argo_workflow_name = argo_workflow_name
            row.updated_at = _utc_now()
            session.commit()

    def update_group_status(self, group_id: str, *, status: str, summary_metrics: dict[str, Any] | None = None) -> None:
        with self._session_factory() as session:
            row = session.get(RiskModelGroup, group_id)
            if row is None or row.family != self._family:
                raise KeyError(f"Risk model group '{group_id}' not found")
            row.status = status
            row.summary_metrics_json = summary_metrics
            row.updated_at = _utc_now()
            session.commit()

    def upsert_target(
        self,
        *,
        group_id: str,
        target_key: str,
        task_type: str,
        status: str,
        model_artifact_path: str | None,
        metrics: dict[str, Any] | None,
        dataset_manifest_path: str | None,
        feature_columns: list[str] | None,
    ) -> None:
        with self._session_factory() as session:
            existing = session.scalar(
                select(RiskModelTarget).where(
                    RiskModelTarget.group_id == group_id,
                    RiskModelTarget.target_key == target_key,
                )
            )
            if existing is None:
                row = RiskModelTarget(
                    group_id=group_id,
                    target_key=target_key,
                    task_type=task_type,
                    status=status,
                    model_artifact_path=model_artifact_path,
                    metrics_json=metrics,
                    dataset_manifest_path=dataset_manifest_path,
                    feature_columns_json=feature_columns,
                )
                session.add(row)
            else:
                existing.task_type = task_type
                existing.status = status
                existing.model_artifact_path = model_artifact_path
                existing.metrics_json = metrics
                existing.dataset_manifest_path = dataset_manifest_path
                existing.feature_columns_json = feature_columns
                existing.updated_at = _utc_now()
            session.commit()

    def list_recent(self, *, limit: int = 100) -> list[RiskModelListItem]:
        with self._session_factory() as session:
            groups = session.scalars(
                select(RiskModelGroup)
                .where(RiskModelGroup.family == self._family)
                .order_by(RiskModelGroup.created_at.desc())
                .limit(limit)
            ).all()
            group_ids = [g.id for g in groups]
            sources = (
                session.query(RiskModelSource)
                .filter(RiskModelSource.group_id.in_(group_ids) if group_ids else False)  # type: ignore[arg-type]
                .all()
            )
            targets = (
                session.query(RiskModelTarget)
                .filter(RiskModelTarget.group_id.in_(group_ids) if group_ids else False)  # type: ignore[arg-type]
                .all()
            )
            target_counts: dict[str, tuple[int, int]] = {}
            if group_ids:
                terminal = {"succeeded", "failed", "canceled"}
                rows = session.execute(
                    select(
                        RiskModelTarget.group_id,
                        func.count(RiskModelTarget.id).label("targets_total"),
                        func.sum(
                            case((RiskModelTarget.status.in_(terminal), 1), else_=0)
                        ).label("targets_done"),
                    )
                    .where(RiskModelTarget.group_id.in_(group_ids))
                    .group_by(RiskModelTarget.group_id)
                ).all()
                for group_id, total, done in rows:
                    target_counts[str(group_id)] = (int(total or 0), int(done or 0))

            backtest_map: dict[str, list[str]] = {}
            for src in sources:
                backtest_map.setdefault(src.group_id, []).append(src.backtest_id)
            target_map: dict[str, list[str]] = {}
            for t in targets:
                target_map.setdefault(t.group_id, []).append(t.target_key)

            training_ranges: dict[str, tuple[date | None, date | None]] = {}
            for group_id in group_ids:
                source_ids = sorted({src.backtest_id for src in sources if src.group_id == group_id})
                training_ranges[group_id] = self._training_date_range(session, source_ids)

            out: list[RiskModelListItem] = []
            for g in groups:
                targets_total, targets_done = target_counts.get(g.id, (0, 0))
                training_start_date, training_end_date = training_ranges.get(g.id, (None, None))
                out.append(
                    RiskModelListItem(
                        group_id=g.id,
                        created_at=g.created_at,
                        updated_at=g.updated_at,
                        status=g.status,
                        argo_namespace=g.argo_namespace,
                        argo_workflow_name=g.argo_workflow_name,
                        backtest_ids=sorted(backtest_map.get(g.id, [])),
                        targets=sorted(set(target_map.get(g.id, []))),
                        targets_total=targets_total,
                        targets_done=targets_done,
                        summary_metrics=g.summary_metrics_json,
                        artifact_dir=g.artifact_dir,
                        training_start_date=training_start_date,
                        training_end_date=training_end_date,
                    )
                )
            return out

    def get_detail(self, group_id: str) -> RiskModelDetail | None:
        with self._session_factory() as session:
            g = session.get(RiskModelGroup, group_id)
            if g is None or g.family != self._family:
                return None
            sources = session.scalars(select(RiskModelSource).where(RiskModelSource.group_id == group_id)).all()
            targets = session.scalars(select(RiskModelTarget).where(RiskModelTarget.group_id == group_id)).all()
            training_start_date, training_end_date = self._training_date_range(
                session,
                [source.backtest_id for source in sources],
            )
            return RiskModelDetail(
                group_id=g.id,
                created_at=g.created_at,
                updated_at=g.updated_at,
                status=g.status,
                argo_namespace=g.argo_namespace,
                argo_workflow_name=g.argo_workflow_name,
                params=g.params_json,
                artifact_dir=g.artifact_dir,
                summary_metrics=g.summary_metrics_json,
                sources=[
                    {
                        "backtest_id": s.backtest_id,
                        "source_report_path": s.source_report_path,
                        "created_at": s.created_at,
                    }
                    for s in sources
                ],
                targets=[
                    RiskModelTargetRow(
                        id=t.id,
                        group_id=t.group_id,
                        target_key=t.target_key,
                        task_type=t.task_type,
                        status=t.status,
                        model_artifact_path=t.model_artifact_path,
                        metrics=t.metrics_json,
                        dataset_manifest_path=t.dataset_manifest_path,
                        feature_columns=t.feature_columns_json,
                        created_at=t.created_at,
                        updated_at=t.updated_at,
                    )
                    for t in targets
                ],
                training_start_date=training_start_date,
                training_end_date=training_end_date,
            )

    def count(self) -> int:
        with self._session_factory() as session:
            return int(
                session.scalar(select(func.count()).select_from(RiskModelGroup).where(RiskModelGroup.family == self._family))
                or 0
            )

    def delete_group(self, group_id: str) -> RiskModelListItem | None:
        with self._session_factory() as session:
            g = session.get(RiskModelGroup, group_id)
            if g is None or g.family != self._family:
                return None
            # Snapshot metadata for caller (e.g. artifact_dir) before delete.
            list_item = RiskModelListItem(
                group_id=g.id,
                created_at=g.created_at,
                updated_at=g.updated_at,
                status=g.status,
                argo_namespace=g.argo_namespace,
                argo_workflow_name=g.argo_workflow_name,
                backtest_ids=[],
                targets=[],
                targets_total=0,
                targets_done=0,
                summary_metrics=g.summary_metrics_json,
                artifact_dir=g.artifact_dir,
                training_start_date=None,
                training_end_date=None,
            )
            session.query(RiskModelTarget).filter(RiskModelTarget.group_id == group_id).delete(
                synchronize_session=False
            )
            session.query(RiskModelSource).filter(RiskModelSource.group_id == group_id).delete(
                synchronize_session=False
            )
            session.query(RiskModelGroup).filter(RiskModelGroup.id == group_id).delete(synchronize_session=False)
            session.commit()
            return list_item
