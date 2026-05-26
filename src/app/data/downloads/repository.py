from __future__ import annotations

import json
import threading
from pathlib import Path

from app.data.downloads.models import (
    DataDownloadDetailResponse,
    DataDownloadRecordResult,
    DataDownloadStatusResponse,
)


class DataDownloadJobRepository:
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir / "data-download-jobs"
        self._lock = threading.Lock()

    def ensure_ready(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def metadata_path(self, job_id: str) -> Path:
        return self.output_dir / f"{job_id}.meta.json"

    def result_path(self, job_id: str) -> Path:
        return self.output_dir / f"{job_id}.result.json"

    def write_metadata(self, item: DataDownloadStatusResponse) -> None:
        self.ensure_ready()
        path = self.metadata_path(item.job_id)
        with self._lock:
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(item.model_dump_json(indent=2), encoding="utf-8")
            temp_path.replace(path)

    def load_metadata(self, job_id: str) -> DataDownloadStatusResponse | None:
        path = self.metadata_path(job_id)
        if not path.exists():
            return None
        return DataDownloadStatusResponse.model_validate_json(path.read_text(encoding="utf-8"))

    def write_results(self, job_id: str, records: list[DataDownloadRecordResult]) -> None:
        self.ensure_ready()
        path = self.result_path(job_id)
        payload = [record.model_dump(mode="json") for record in records]
        with self._lock:
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            temp_path.replace(path)

    def load_results(self, job_id: str) -> list[DataDownloadRecordResult]:
        path = self.result_path(job_id)
        if not path.exists():
            return []
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            return []
        return [DataDownloadRecordResult.model_validate(item) for item in raw]

    def list_jobs(self) -> list[DataDownloadStatusResponse]:
        self.ensure_ready()
        items: list[DataDownloadStatusResponse] = []
        for path in self.output_dir.glob("*.meta.json"):
            job_id = path.name[: -len(".meta.json")]
            metadata = self.load_metadata(job_id)
            if metadata is not None:
                items.append(metadata)
        items.sort(key=lambda item: item.created_at, reverse=True)
        return items

    def get_detail(self, job_id: str) -> DataDownloadDetailResponse | None:
        metadata = self.load_metadata(job_id)
        if metadata is None:
            return None
        return DataDownloadDetailResponse(
            metadata=metadata,
            records=self.load_results(job_id),
        )

    def delete(self, job_id: str) -> bool:
        metadata_path = self.metadata_path(job_id)
        result_path = self.result_path(job_id)
        existed = metadata_path.exists() or result_path.exists()
        metadata_path.unlink(missing_ok=True)
        result_path.unlink(missing_ok=True)
        return existed
