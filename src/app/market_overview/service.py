from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from app.market_overview.argo import MarketOverviewArgoSubmitter
from app.market_overview.argo_workflow import workflow_artifact_paths, workflow_results_mount
from app.market_overview.models import MarketOverviewCreateRequest, MarketOverviewSnapshot
from app.market_overview.persistence import SqlAlchemyMarketOverviewRepository
from app.settings.models import PlatformSettings
from app.settings.service import PlatformSettingsService


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class MarketOverviewLaunchResult:
    snapshot_id: str
    status: str
    argo_namespace: str
    argo_workflow_name: str
    output_path: str


class MarketOverviewService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        repo: SqlAlchemyMarketOverviewRepository,
        argo_submitter: MarketOverviewArgoSubmitter | None = None,
        settings_service: PlatformSettingsService | None = None,
    ):
        self._session_factory = session_factory
        self._repo = repo
        self._argo_submitter = argo_submitter or MarketOverviewArgoSubmitter()
        self._settings_service = settings_service
        self._logger = logging.getLogger(__name__)

    def _utc_now(self) -> datetime:
        return _utc_now()

    def _default_params(self) -> dict[str, object]:
        settings: PlatformSettings | None = None
        if self._settings_service is not None:
            settings = self._settings_service.load()
        interval = None
        if settings is not None:
            interval = settings.platform_behavior.market_overview_refresh_interval_seconds
        return {"refresh_interval_seconds": interval}

    def _artifact_dir(self, snapshot_id: str) -> str:
        return f"{workflow_results_mount()}/{snapshot_id}"

    def create_and_submit_argo(self, request: MarketOverviewCreateRequest | None = None) -> MarketOverviewLaunchResult:
        snapshot_id = uuid.uuid4().hex
        params = self._default_params()
        name = request.name.strip() if request and request.name and request.name.strip() else None
        as_of = request.as_of if request else None
        output_path = workflow_artifact_paths(snapshot_id)[1]
        now = self._utc_now()
        launch = MarketOverviewSnapshot(
            snapshot_id=snapshot_id,
            name=name,
            status="running",
            as_of=as_of,
            params=params,
            created_at=now,
            updated_at=now,
        )
        self._repo.upsert(launch)
        wf_name, wf_ns = self._argo_submitter.submit(snapshot_id=snapshot_id, output_path=output_path)
        launch.argo_namespace = wf_ns
        launch.argo_workflow_name = wf_name
        self._repo.upsert(launch)
        return MarketOverviewLaunchResult(
            snapshot_id=snapshot_id,
            status="running",
            argo_namespace=wf_ns,
            argo_workflow_name=wf_name,
            output_path=output_path,
        )

    def launch_if_due(self) -> MarketOverviewLaunchResult | None:
        settings = self._settings_service.load() if self._settings_service is not None else None
        interval_seconds = (
            settings.platform_behavior.market_overview_refresh_interval_seconds if settings is not None else None
        )
        latest = self._repo.get_latest()
        if latest is not None and interval_seconds is not None:
            # Keep cadence driven by the saved UI setting.
            age = (self._utc_now() - latest.updated_at).total_seconds()
            if age < interval_seconds and latest.status in {"pending", "running", "completed"}:
                return None
        return self.create_and_submit_argo(MarketOverviewCreateRequest())

    def refresh_from_artifact(self, snapshot_id: str) -> MarketOverviewSnapshot | None:
        _, json_path = workflow_artifact_paths(snapshot_id)
        path = Path(json_path)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        snapshot = MarketOverviewSnapshot.model_validate(payload)
        self._repo.upsert(snapshot)
        return snapshot

    def get_latest(self) -> MarketOverviewSnapshot | None:
        return self._repo.get_latest()

    def list_recent(self, *, limit: int = 100) -> list[MarketOverviewSnapshot]:
        return self._repo.list_recent(limit=limit)

    def get(self, snapshot_id: str) -> MarketOverviewSnapshot | None:
        return self._repo.get(snapshot_id)
