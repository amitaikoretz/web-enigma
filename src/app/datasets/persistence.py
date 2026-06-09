from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import shutil
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.datasets.models import DatasetListItem
from app.db.models import DatasetJob


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_symbols_from_item(item: DatasetListItem) -> list[str]:
    symbols = [value.strip().upper() for value in item.symbols if value.strip()]
    if not symbols and item.symbol.strip():
        symbols = [item.symbol.strip().upper()]
    seen: set[str] = set()
    normalized: list[str] = []
    for symbol in symbols:
        if symbol not in seen:
            seen.add(symbol)
            normalized.append(symbol)
    return normalized


def _artifact_slug(item: DatasetListItem) -> str:
    symbols = item.symbols or ([item.symbol] if item.symbol.strip() else [])
    normalized = _normalize_symbols_from_item(item) if symbols else []
    return "-".join(normalized) if normalized else (item.symbol.strip().upper() or item.id)


def _artifact_directories(item: DatasetListItem, root: Path) -> list[Path]:
    dated_dir = root / item.created_at.date().isoformat() / item.id
    legacy_dir = root / item.id
    return [dated_dir, legacy_dir] if dated_dir != legacy_dir else [legacy_dir]


@dataclass(frozen=True)
class DatasetArtifactPaths:
    dataset_parquet_path: str | None = None
    manifest_path: str | None = None


class SqlAlchemyDatasetRepository:
    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def create(self, item: DatasetListItem) -> None:
        with self._session_factory() as session:
            row = DatasetJob(
                id=item.id,
                name=item.name,
                symbol=item.symbol,
                provider=item.provider,
                resolution=item.resolution,
                start_date=item.start_date,
                end_date=item.end_date,
                status=item.status,
                argo_namespace=item.argo_namespace,
                argo_workflow_name=item.argo_workflow_name,
                params_json=item.params_json,
                output_dir=item.output_dir,
                dataset_parquet_path=item.dataset_parquet_path,
                manifest_path=item.manifest_path,
                options_parquet_path=item.options_parquet_path,
                options_manifest_path=item.options_manifest_path,
                error_message=item.error_message,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            session.add(row)
            session.commit()

    def update(self, item: DatasetListItem) -> None:
        with self._session_factory() as session:
            row = session.get(DatasetJob, item.id)
            if row is None:
                raise KeyError(f"Dataset job '{item.id}' not found")
            row.name = item.name
            row.symbol = item.symbol
            row.provider = item.provider
            row.resolution = item.resolution
            row.start_date = item.start_date
            row.end_date = item.end_date
            row.status = item.status
            row.argo_namespace = item.argo_namespace
            row.argo_workflow_name = item.argo_workflow_name
            row.params_json = item.params_json
            row.output_dir = item.output_dir
            row.dataset_parquet_path = item.dataset_parquet_path
            row.manifest_path = item.manifest_path
            row.options_parquet_path = item.options_parquet_path
            row.options_manifest_path = item.options_manifest_path
            row.error_message = item.error_message
            row.updated_at = _utc_now()
            session.commit()

    def get(self, dataset_id: str) -> DatasetListItem | None:
        with self._session_factory() as session:
            row = session.get(DatasetJob, dataset_id)
            if row is None:
                return None
            params_symbols = row.params_json.get("symbols") if isinstance(row.params_json, dict) else None
            symbols = []
            if isinstance(params_symbols, list):
                symbols = [value.strip().upper() for value in params_symbols if isinstance(value, str) and value.strip()]
            if not symbols and row.symbol.strip():
                symbols = [row.symbol.strip().upper()]
            return DatasetListItem(
                id=row.id,
                name=row.name,
                symbol=row.symbol,
                symbols=symbols,
                provider=row.provider,
                resolution=row.resolution,
                start_date=row.start_date,
                end_date=row.end_date,
                created_at=row.created_at,
                updated_at=row.updated_at,
                status=row.status,  # type: ignore[arg-type]
                argo_namespace=row.argo_namespace,
                argo_workflow_name=row.argo_workflow_name,
                params_json=row.params_json,
                output_dir=row.output_dir,
                dataset_parquet_path=row.dataset_parquet_path,
                manifest_path=row.manifest_path,
                options_parquet_path=row.options_parquet_path,
                options_manifest_path=row.options_manifest_path,
                error_message=row.error_message,
                progress_pct=100.0 if row.status in {"completed", "failed"} else 0.0,
            )

    def list_recent(self, *, limit: int = 100) -> list[DatasetListItem]:
        with self._session_factory() as session:
            rows = session.scalars(select(DatasetJob).order_by(DatasetJob.created_at.desc()).limit(limit)).all()
            return [
                DatasetListItem(
                    id=row.id,
                    name=row.name,
                    symbol=row.symbol,
                    symbols=(
                        [value.strip().upper() for value in row.params_json.get("symbols", []) if isinstance(value, str) and value.strip()]
                        if isinstance(row.params_json, dict)
                        else []
                    )
                    or [row.symbol.strip().upper()],
                    provider=row.provider,
                    resolution=row.resolution,
                    start_date=row.start_date,
                    end_date=row.end_date,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    status=row.status,  # type: ignore[arg-type]
                    argo_namespace=row.argo_namespace,
                    argo_workflow_name=row.argo_workflow_name,
                    params_json=row.params_json,
                    output_dir=row.output_dir,
                    dataset_parquet_path=row.dataset_parquet_path,
                    manifest_path=row.manifest_path,
                    options_parquet_path=row.options_parquet_path,
                    options_manifest_path=row.options_manifest_path,
                    error_message=row.error_message,
                    progress_pct=100.0 if row.status in {"completed", "failed"} else 0.0,
                )
                for row in rows
            ]

    def count(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(DatasetJob)) or 0)

    def delete(self, dataset_id: str) -> DatasetListItem | None:
        with self._session_factory() as session:
            row = session.get(DatasetJob, dataset_id)
            if row is None:
                return None
            params_symbols = row.params_json.get("symbols") if isinstance(row.params_json, dict) else None
            symbols = []
            if isinstance(params_symbols, list):
                symbols = [value.strip().upper() for value in params_symbols if isinstance(value, str) and value.strip()]
            if not symbols and row.symbol.strip():
                symbols = [row.symbol.strip().upper()]
            item = DatasetListItem(
                id=row.id,
                name=row.name,
                symbol=row.symbol,
                symbols=symbols,
                provider=row.provider,
                resolution=row.resolution,
                start_date=row.start_date,
                end_date=row.end_date,
                created_at=row.created_at,
                updated_at=row.updated_at,
                status=row.status,  # type: ignore[arg-type]
                argo_namespace=row.argo_namespace,
                argo_workflow_name=row.argo_workflow_name,
                params_json=row.params_json,
                output_dir=row.output_dir,
                dataset_parquet_path=row.dataset_parquet_path,
                manifest_path=row.manifest_path,
                options_parquet_path=row.options_parquet_path,
                options_manifest_path=row.options_manifest_path,
                error_message=row.error_message,
                progress_pct=100.0 if row.status in {"completed", "failed"} else 0.0,
            )
            session.delete(row)
            session.commit()
            return item

    def delete_artifacts(self, item: DatasetListItem) -> bool:
        deleted = False

        candidates: list[Path] = []
        if item.output_dir:
            root = Path(item.output_dir).resolve()
            candidates.extend(_artifact_directories(item, root))
            artifact_slug = _artifact_slug(item)
            candidates.extend(
                [
                    root / f"{artifact_slug}-{item.provider}-{item.resolution}.parquet",
                    root / f"{artifact_slug}-{item.provider}-{item.resolution}.manifest.json",
                    root / f"{artifact_slug}-alpaca-options-{item.resolution}.parquet",
                    root / f"{artifact_slug}-alpaca-options-{item.resolution}.manifest.json",
                ]
            )

        for path_str in [
            item.dataset_parquet_path,
            item.manifest_path,
            item.options_parquet_path,
            item.options_manifest_path,
        ]:
            if path_str:
                candidates.append(Path(path_str))

        seen: set[str] = set()
        for candidate in candidates:
            resolved = str(candidate)
            if resolved in seen:
                continue
            seen.add(resolved)
            if candidate.is_dir():
                shutil.rmtree(candidate)
                deleted = True
                continue
            if candidate.is_file():
                candidate.unlink()
                deleted = True

        return deleted
