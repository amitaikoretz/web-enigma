from __future__ import annotations

import json
from pathlib import Path
import shutil

from app.scans.models import ScanStatusResponse, ScanType


class ScanJobRepository:
    def __init__(self, output_dir: Path):
        self.base_dir = output_dir / "scan-jobs"

    def scan_dir(self, scan_type: ScanType, scan_id: str) -> Path:
        return self.base_dir / scan_type / scan_id

    def metadata_path(self, scan_type: ScanType, scan_id: str) -> Path:
        return self.scan_dir(scan_type, scan_id) / "metadata.json"

    def results_path(self, scan_type: ScanType, scan_id: str) -> Path:
        return self.scan_dir(scan_type, scan_id) / "results.json"

    def write_metadata(self, item: ScanStatusResponse) -> None:
        path = self.metadata_path(item.scan_type, item.scan_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(item.model_dump_json(indent=2), encoding="utf-8")

    def load_metadata(self, scan_type: ScanType, scan_id: str) -> ScanStatusResponse | None:
        path = self.metadata_path(scan_type, scan_id)
        if not path.exists():
            return None
        return ScanStatusResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def list_scans(self, scan_type: ScanType) -> list[ScanStatusResponse]:
        base = self.base_dir / scan_type
        if not base.exists():
            return []
        items: list[ScanStatusResponse] = []
        for path in base.glob("*/metadata.json"):
            try:
                items.append(ScanStatusResponse.model_validate_json(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def cleanup_keep_last(self, scan_type: ScanType, keep: int = 10) -> None:
        items = self.list_scans(scan_type)
        if len(items) <= keep:
            return
        for item in items[keep:]:
            dir_path = self.scan_dir(scan_type, item.scan_id)
            if dir_path.exists():
                shutil.rmtree(dir_path, ignore_errors=True)

    def write_results_json(self, scan_type: ScanType, scan_id: str, payload: dict) -> None:
        path = self.results_path(scan_type, scan_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
