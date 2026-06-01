from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.scans.models import ScanStatusResponse
from app.scans.repository import ScanJobRepository


def _mk_item(scan_id: str, created_at: datetime) -> ScanStatusResponse:
    return ScanStatusResponse(
        scan_id=scan_id,
        scan_type="momentum",
        status="completed",
        created_at=created_at,
        updated_at=created_at,
        params={},
        results_json_path=None,
    )


def test_cleanup_keep_last_removes_old_runs(tmp_path) -> None:
    repo = ScanJobRepository(tmp_path)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for i in range(12):
        item = _mk_item(f"scan-{i}", start + timedelta(minutes=i))
        repo.write_metadata(item)
        repo.write_results_json(item.scan_type, item.scan_id, {"i": i})

    repo.cleanup_keep_last("momentum", keep=10)
    remaining = repo.list_scans("momentum")
    assert len(remaining) == 10
    assert remaining[0].scan_id == "scan-11"
    assert remaining[-1].scan_id == "scan-2"

