from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import DailyIndexFeatureRun, RiskModelGroup, RiskModelTarget
from app.daily_index_forecast.models import DailyIndexForecastDatasetManifestSummary
from app.feature_importance.models import FeatureImportanceTarget


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _start_of_day(value: date) -> datetime:
    return datetime.combine(value, time.min).replace(tzinfo=None)


@dataclass(frozen=True)
class DailyIndexFeatureRunRow:
    feature_run_id: str
    symbol: str
    benchmark_symbol: str | None
    decision_times: list[str]
    start_date: date
    end_date: date
    status: str
    argo_namespace: str | None
    argo_workflow_name: str | None
    params: dict[str, Any]
    artifact_dir: str
    manifest_path: str | None
    features_parquet_path: str | None
    labels_parquet_path: str | None
    summary_metrics: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class DailyIndexModelTargetRow:
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
    feature_importance: FeatureImportanceTarget | None = None


@dataclass(frozen=True)
class DailyIndexModelListItem:
    group_id: str
    feature_run_id: str
    name: str | None
    created_at: datetime
    updated_at: datetime
    status: str
    argo_namespace: str | None
    argo_workflow_name: str | None
    symbol: str
    benchmark_symbol: str | None
    decision_times: list[str]
    start_date: date
    end_date: date
    targets: list[str]
    targets_total: int
    targets_done: int
    summary_metrics: dict[str, Any] | None
    artifact_dir: str
    feature_run_artifact_dir: str


@dataclass(frozen=True)
class DailyIndexModelDetail:
    group_id: str
    feature_run_id: str
    name: str | None
    created_at: datetime
    updated_at: datetime
    status: str
    argo_namespace: str | None
    argo_workflow_name: str | None
    params: dict[str, Any]
    artifact_dir: str
    summary_metrics: dict[str, Any] | None
    feature_run: DailyIndexFeatureRunRow | None
    targets: list[DailyIndexModelTargetRow]
    feature_importance: FeatureImportanceTarget | None = None


class SqlAlchemyDailyIndexForecastRepository:
    def __init__(self, session_factory: sessionmaker[Session], *, family: str = "daily_index_forecast"):
        self._session_factory = session_factory
        self._family = family

    def create_feature_run(
        self,
        *,
        feature_run_id: str,
        symbol: str,
        benchmark_symbol: str | None,
        decision_times: list[str],
        start_date: date,
        end_date: date,
        status: str,
        params: dict[str, Any],
        artifact_dir: str,
        manifest_path: str | None = None,
        features_parquet_path: str | None = None,
        labels_parquet_path: str | None = None,
        summary_metrics: dict[str, Any] | None = None,
        argo_namespace: str | None = None,
        argo_workflow_name: str | None = None,
    ) -> None:
        now = _utc_now()
        with self._session_factory() as session:
            row = DailyIndexFeatureRun(
                id=feature_run_id,
                symbol=symbol,
                benchmark_symbol=benchmark_symbol,
                decision_times_json=decision_times,
                start_date=start_date,
                end_date=end_date,
                status=status,
                argo_namespace=argo_namespace,
                argo_workflow_name=argo_workflow_name,
                params_json=params,
                artifact_dir=artifact_dir,
                manifest_path=manifest_path,
                features_parquet_path=features_parquet_path,
                labels_parquet_path=labels_parquet_path,
                summary_metrics_json=summary_metrics,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()

    def update_feature_run_workflow(self, feature_run_id: str, *, argo_namespace: str, argo_workflow_name: str) -> None:
        with self._session_factory() as session:
            row = session.get(DailyIndexFeatureRun, feature_run_id)
            if row is None:
                raise KeyError(f"Daily index feature run '{feature_run_id}' not found")
            row.argo_namespace = argo_namespace
            row.argo_workflow_name = argo_workflow_name
            row.updated_at = _utc_now()
            session.commit()

    def update_feature_run_status(
        self,
        feature_run_id: str,
        *,
        status: str,
        summary_metrics: dict[str, Any] | None = None,
        manifest_path: str | None = None,
        features_parquet_path: str | None = None,
        labels_parquet_path: str | None = None,
    ) -> None:
        with self._session_factory() as session:
            row = session.get(DailyIndexFeatureRun, feature_run_id)
            if row is None:
                raise KeyError(f"Daily index feature run '{feature_run_id}' not found")
            row.status = status
            row.summary_metrics_json = summary_metrics
            if manifest_path is not None:
                row.manifest_path = manifest_path
            if features_parquet_path is not None:
                row.features_parquet_path = features_parquet_path
            if labels_parquet_path is not None:
                row.labels_parquet_path = labels_parquet_path
            row.updated_at = _utc_now()
            session.commit()

    def get_feature_run(self, feature_run_id: str) -> DailyIndexFeatureRunRow | None:
        with self._session_factory() as session:
            row = session.get(DailyIndexFeatureRun, feature_run_id)
            if row is None:
                return None
            return DailyIndexFeatureRunRow(
                feature_run_id=row.id,
                symbol=row.symbol,
                benchmark_symbol=row.benchmark_symbol,
                decision_times=list(row.decision_times_json or []),
                start_date=row.start_date,
                end_date=row.end_date,
                status=row.status,
                argo_namespace=row.argo_namespace,
                argo_workflow_name=row.argo_workflow_name,
                params=row.params_json,
                artifact_dir=row.artifact_dir,
                manifest_path=row.manifest_path,
                features_parquet_path=row.features_parquet_path,
                labels_parquet_path=row.labels_parquet_path,
                summary_metrics=row.summary_metrics_json,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )

    def create_group(
        self,
        *,
        group_id: str,
        feature_run_id: str,
        name: str | None,
        status: str,
        params: dict[str, Any],
        artifact_dir: str,
        argo_namespace: str | None = None,
        argo_workflow_name: str | None = None,
    ) -> None:
        now = _utc_now()
        with self._session_factory() as session:
            row = RiskModelGroup(
                id=group_id,
                family=self._family,
                name=name,
                status=status,
                argo_namespace=argo_namespace,
                argo_workflow_name=argo_workflow_name,
                feature_run_id=feature_run_id,
                params_json=params,
                artifact_dir=artifact_dir,
                summary_metrics_json=None,
                created_at=now,
                updated_at=now,
            )
            session.add(row)
            session.commit()

    def update_group_workflow(self, group_id: str, *, argo_namespace: str, argo_workflow_name: str) -> None:
        with self._session_factory() as session:
            row = session.get(RiskModelGroup, group_id)
            if row is None or row.family != self._family:
                raise KeyError(f"Daily index forecast group '{group_id}' not found")
            row.argo_namespace = argo_namespace
            row.argo_workflow_name = argo_workflow_name
            row.updated_at = _utc_now()
            session.commit()

    def update_group_name(self, group_id: str, name: str | None) -> DailyIndexModelDetail | None:
        with self._session_factory() as session:
            row = session.get(RiskModelGroup, group_id)
            if row is None or row.family != self._family:
                return None
            row.name = name
            params = dict(row.params_json or {})
            if name is None:
                params.pop("name", None)
            else:
                params["name"] = name
            row.params_json = params
            row.updated_at = _utc_now()
            session.commit()
        return self.get_detail(group_id)

    def update_group_status(self, group_id: str, *, status: str, summary_metrics: dict[str, Any] | None = None) -> None:
        with self._session_factory() as session:
            row = session.get(RiskModelGroup, group_id)
            if row is None or row.family != self._family:
                raise KeyError(f"Daily index forecast group '{group_id}' not found")
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

    def list_recent(self, *, limit: int = 100) -> list[DailyIndexModelListItem]:
        with self._session_factory() as session:
            groups = session.scalars(
                select(RiskModelGroup)
                .where(RiskModelGroup.family == self._family)
                .order_by(RiskModelGroup.created_at.desc())
                .limit(limit)
            ).all()
            group_ids = [g.id for g in groups]
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
                        func.sum(case((RiskModelTarget.status.in_(terminal), 1), else_=0)).label("targets_done"),
                    )
                    .where(RiskModelTarget.group_id.in_(group_ids))
                    .group_by(RiskModelTarget.group_id)
                ).all()
                for group_id, total, done in rows:
                    target_counts[str(group_id)] = (int(total or 0), int(done or 0))

            target_map: dict[str, list[str]] = {}
            for t in targets:
                target_map.setdefault(t.group_id, []).append(t.target_key)

            out: list[DailyIndexModelListItem] = []
            for g in groups:
                feature_run = session.get(DailyIndexFeatureRun, g.feature_run_id) if g.feature_run_id else None
                if feature_run is None:
                    continue
                targets_total, targets_done = target_counts.get(g.id, (0, 0))
                out.append(
                    DailyIndexModelListItem(
                        group_id=g.id,
                        feature_run_id=g.feature_run_id or "",
                        name=g.name,
                        created_at=g.created_at,
                        updated_at=g.updated_at,
                        status=g.status,
                        argo_namespace=g.argo_namespace,
                        argo_workflow_name=g.argo_workflow_name,
                        symbol=feature_run.symbol,
                        benchmark_symbol=feature_run.benchmark_symbol,
                        decision_times=list(feature_run.decision_times_json or []),
                        start_date=feature_run.start_date,
                        end_date=feature_run.end_date,
                        targets=sorted(set(target_map.get(g.id, []))),
                        targets_total=targets_total,
                        targets_done=targets_done,
                        summary_metrics=g.summary_metrics_json,
                        artifact_dir=g.artifact_dir,
                        feature_run_artifact_dir=feature_run.artifact_dir,
                    )
                )
            return out

    def get_detail(self, group_id: str) -> DailyIndexModelDetail | None:
        with self._session_factory() as session:
            g = session.get(RiskModelGroup, group_id)
            if g is None or g.family != self._family:
                return None
            feature_run = session.get(DailyIndexFeatureRun, g.feature_run_id) if g.feature_run_id else None
            targets = session.scalars(select(RiskModelTarget).where(RiskModelTarget.group_id == group_id)).all()
            feature_run_row = None
            if feature_run is not None:
                feature_run_row = DailyIndexFeatureRunRow(
                    feature_run_id=feature_run.id,
                    symbol=feature_run.symbol,
                    benchmark_symbol=feature_run.benchmark_symbol,
                    decision_times=list(feature_run.decision_times_json or []),
                    start_date=feature_run.start_date,
                    end_date=feature_run.end_date,
                    status=feature_run.status,
                    argo_namespace=feature_run.argo_namespace,
                    argo_workflow_name=feature_run.argo_workflow_name,
                    params=feature_run.params_json,
                    artifact_dir=feature_run.artifact_dir,
                    manifest_path=feature_run.manifest_path,
                    features_parquet_path=feature_run.features_parquet_path,
                    labels_parquet_path=feature_run.labels_parquet_path,
                    summary_metrics=feature_run.summary_metrics_json,
                    created_at=feature_run.created_at,
                    updated_at=feature_run.updated_at,
                )
            return DailyIndexModelDetail(
                group_id=g.id,
                feature_run_id=g.feature_run_id or "",
                name=g.name,
                created_at=g.created_at,
                updated_at=g.updated_at,
                status=g.status,
                argo_namespace=g.argo_namespace,
                argo_workflow_name=g.argo_workflow_name,
                params=g.params_json,
                artifact_dir=g.artifact_dir,
                summary_metrics=g.summary_metrics_json,
                feature_run=feature_run_row,
                targets=[
                    DailyIndexModelTargetRow(
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
            )

    def delete_group(self, group_id: str) -> DailyIndexModelListItem | None:
        with self._session_factory() as session:
            g = session.get(RiskModelGroup, group_id)
            if g is None or g.family != self._family:
                return None
            feature_run = session.get(DailyIndexFeatureRun, g.feature_run_id) if g.feature_run_id else None
            list_item = DailyIndexModelListItem(
                group_id=g.id,
                feature_run_id=g.feature_run_id or "",
                name=g.name,
                created_at=g.created_at,
                updated_at=g.updated_at,
                status=g.status,
                argo_namespace=g.argo_namespace,
                argo_workflow_name=g.argo_workflow_name,
                symbol=feature_run.symbol if feature_run is not None else "",
                benchmark_symbol=feature_run.benchmark_symbol if feature_run is not None else None,
                decision_times=list(feature_run.decision_times_json or []) if feature_run is not None else [],
                start_date=feature_run.start_date if feature_run is not None else date.today(),
                end_date=feature_run.end_date if feature_run is not None else date.today(),
                targets=[],
                targets_total=0,
                targets_done=0,
                summary_metrics=g.summary_metrics_json,
                artifact_dir=g.artifact_dir,
                feature_run_artifact_dir=feature_run.artifact_dir if feature_run is not None else "",
            )
            session.query(RiskModelTarget).filter(RiskModelTarget.group_id == group_id).delete(synchronize_session=False)
            if g.feature_run_id:
                session.query(DailyIndexFeatureRun).filter(DailyIndexFeatureRun.id == g.feature_run_id).delete(
                    synchronize_session=False
                )
            session.query(RiskModelGroup).filter(RiskModelGroup.id == group_id).delete(synchronize_session=False)
            session.commit()
            return list_item
