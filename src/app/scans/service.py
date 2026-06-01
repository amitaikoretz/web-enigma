from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from app.scans.argo import ScanArgoSubmitter
from app.scans.models import ScanCreateRequest, ScanStatusResponse, ScanType, utc_now
from app.scans.params import parse_scan_params
from app.scans.repository import ScanJobRepository


_PHASE_TO_STATUS = {
    "Pending": "pending",
    "Running": "running",
    "Succeeded": "completed",
    "Failed": "failed",
    "Error": "failed",
}


class ScanJobService:
    def __init__(self, repo: ScanJobRepository, *, argo_submitter: ScanArgoSubmitter, output_dir: Path):
        self.repo = repo
        self.argo = argo_submitter
        self.output_dir = output_dir

    def create_scan(self, scan_type: ScanType, request: ScanCreateRequest) -> ScanStatusResponse:
        if not self.argo.is_configured:
            raise RuntimeError("Argo workflows are not configured; set ARGO_SERVER_URL (and token if needed).")

        params_model = parse_scan_params(scan_type, request.params)
        scan_id = uuid.uuid4().hex
        created_at = utc_now()
        item = ScanStatusResponse(
            scan_id=scan_id,
            scan_type=scan_type,
            status="pending",
            created_at=created_at,
            updated_at=created_at,
            params=params_model.model_dump(),
        )
        self.repo.write_metadata(item)
        # Enforce retention proactively so we never accumulate more than the last 10 runs per type.
        self.cleanup(scan_type, keep=10)

        results_path = str(self.repo.results_path(scan_type, scan_id))
        params_json = params_model.model_dump_json()
        workflow_name, namespace = self.argo.submit(
            scan_type=scan_type,
            scan_id=scan_id,
            results_path=results_path,
            params_json=params_json,
        )
        item.argo_workflow_name = workflow_name
        item.argo_namespace = namespace
        item.updated_at = utc_now()
        item.results_json_path = results_path
        self.repo.write_metadata(item)
        return item

    def get_scan(self, scan_type: ScanType, scan_id: str) -> ScanStatusResponse | None:
        item = self.repo.load_metadata(scan_type, scan_id)
        if item is None:
            return None
        self._refresh_from_argo(item)
        return item

    def list_scans(self, scan_type: ScanType, limit: int = 10) -> list[ScanStatusResponse]:
        items = self.repo.list_scans(scan_type)[: max(0, limit)]
        for item in items:
            self._refresh_from_argo(item, write_back=False)
        return items

    def cleanup(self, scan_type: ScanType, keep: int = 10) -> None:
        self.repo.cleanup_keep_last(scan_type, keep=keep)

    def _refresh_from_argo(self, item: ScanStatusResponse, *, write_back: bool = True) -> None:
        if not item.argo_workflow_name:
            return
        phase = self.argo.get_workflow_phase(item.argo_workflow_name)
        if phase is None:
            return
        new_status = _PHASE_TO_STATUS.get(phase)
        if new_status is None or new_status == item.status:
            return
        item.status = new_status  # type: ignore[assignment]
        item.updated_at = utc_now()
        if write_back:
            self.repo.write_metadata(item)
            if item.status in {"completed", "failed"}:
                self.cleanup(item.scan_type, keep=10)
