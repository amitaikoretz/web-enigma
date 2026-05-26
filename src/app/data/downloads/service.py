from __future__ import annotations

import os
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.config.models import AlpacaDataSource, DataCacheConfig
from app.data.cache import CacheKey, ParquetDataCache
from app.data.downloads.models import (
    DataDownloadCreateRequest,
    DataDownloadCreateResponse,
    DataDownloadDetailResponse,
    DataDownloadRecord,
    DataDownloadRecordResult,
    DataDownloadStatusResponse,
)
from app.data.downloads.repository import DataDownloadJobRepository
from app.data.loaders import build_alpaca_data_feed_with_cache


class InvalidOutputFolderError(ValueError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def allowed_cache_roots(cache_config: DataCacheConfig) -> list[Path]:
    roots: list[Path] = [Path(cache_config.directory).resolve()]
    env_cache_dir = os.environ.get("BACKTEST_CACHE_DIR")
    if env_cache_dir:
        env_root = Path(env_cache_dir).resolve()
        if env_root not in roots:
            roots.append(env_root)
    return roots


def resolve_output_folder(output_folder: str, cache_config: DataCacheConfig) -> Path:
    candidate = Path(output_folder).expanduser().resolve()
    allowed = allowed_cache_roots(cache_config)
    if not any(candidate == root or root in candidate.parents for root in allowed):
        allowed_display = ", ".join(str(root) for root in allowed)
        raise InvalidOutputFolderError(
            f"output_folder must be under an allowed cache root: {allowed_display}"
        )
    return candidate


class DataDownloadJobService:
    def __init__(self, repository: DataDownloadJobRepository, cache_config: DataCacheConfig):
        self.repository = repository
        self.cache_config = cache_config

    def submit(self, payload: DataDownloadCreateRequest) -> DataDownloadCreateResponse:
        output_folder = resolve_output_folder(payload.output_folder, self.cache_config)
        output_folder.mkdir(parents=True, exist_ok=True)

        job_id = uuid.uuid4().hex
        created_at = _utc_now()
        metadata = DataDownloadStatusResponse(
            job_id=job_id,
            status="pending",
            output_folder=str(output_folder),
            total_records=len(payload.records),
            created_at=created_at,
            updated_at=created_at,
        )
        self.repository.write_metadata(metadata)
        self.repository.write_results(job_id, [])

        worker = threading.Thread(
            target=self._run_job,
            args=(metadata, payload.records, output_folder),
            daemon=True,
            name=f"data-download-job-{job_id}",
        )
        worker.start()

        return DataDownloadCreateResponse(
            job_id=job_id,
            status="pending",
            status_url=f"/market-data/downloads/{job_id}/status",
            detail_url=f"/market-data/downloads/{job_id}",
        )

    def list_jobs(self) -> list[DataDownloadStatusResponse]:
        return self.repository.list_jobs()

    def get_status(self, job_id: str) -> DataDownloadStatusResponse | None:
        return self.repository.load_metadata(job_id)

    def get_detail(self, job_id: str) -> DataDownloadDetailResponse | None:
        return self.repository.get_detail(job_id)

    def _run_job(
        self,
        metadata: DataDownloadStatusResponse,
        records: list[DataDownloadRecord],
        output_folder: Path,
    ) -> None:
        current = metadata.model_copy(deep=True)
        current.status = "running"
        current.updated_at = _utc_now()
        self.repository.write_metadata(current)

        cache_config = self.cache_config.model_copy(
            update={"directory": str(output_folder), "enabled": True}
        )
        results: list[DataDownloadRecordResult] = []

        try:
            for record in records:
                result = self._process_record(record, cache_config, output_folder)
                results.append(result)
                current.completed_records += 1
                if result.error is None:
                    current.successful_records += 1
                else:
                    current.failed_records += 1
                current.updated_at = _utc_now()
                self.repository.write_metadata(current)
                self.repository.write_results(current.job_id, results)

            current.status = "completed"
            current.updated_at = _utc_now()
            self.repository.write_metadata(current)
        except Exception as exc:  # noqa: BLE001
            current.status = "failed"
            current.error_message = str(exc)
            current.updated_at = _utc_now()
            self.repository.write_metadata(current)
            self.repository.write_results(current.job_id, results)

    def _process_record(
        self,
        record: DataDownloadRecord,
        cache_config: DataCacheConfig,
        output_folder: Path,
    ) -> DataDownloadRecordResult:
        base = DataDownloadRecordResult(
            symbol=record.symbol,
            start_date=record.start_date,
            stop_date=record.stop_date,
            resolution=record.resolution,
            feed=record.feed,
        )
        data_source = AlpacaDataSource(
            type="alpaca",
            symbol=record.symbol,
            interval=record.resolution,
            feed=record.feed,
        )
        try:
            frame, cache_status = build_alpaca_data_feed_with_cache(
                data_source,
                record.start_date,
                record.stop_date,
                cache_config,
                force_refresh=record.force_refresh,
            )
            cache_key = CacheKey(
                source="alpaca",
                symbol=record.symbol,
                interval=record.resolution,
                start_date=record.start_date.isoformat(),
                end_date=record.stop_date.isoformat(),
                feed=record.feed,
            )
            parquet_path = ParquetDataCache(output_folder).path_for(cache_key)
            return base.model_copy(
                update={
                    "cache_status": cache_status,
                    "parquet_path": str(parquet_path),
                    "row_count": len(frame),
                }
            )
        except RuntimeError as exc:
            return base.model_copy(update={"error": str(exc)})
