from __future__ import annotations

from datetime import date, datetime, UTC
from pathlib import Path

import pandas as pd

from app.datasets.models import DatasetArtifactManifest, DatasetChunkRecord
from app.datasets.reader import DatasetArtifactReader


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _real_manifest_path() -> Path:
    return (
        _repo_root()
        / "data"
        / "backtest-results"
        / "2026-06-09"
        / "e691de3d7f5b46838340a6e75da75acf"
        / "6323b5739854-alpaca-1m.manifest.json"
    )


def _real_dataset_path() -> Path:
    return _real_manifest_path().with_name("6323b5739854-alpaca-1m.parquet")


def test_dataset_artifact_reader_loads_real_manifest_and_combined_parquet() -> None:
    manifest_path = _real_manifest_path()
    dataset_path = _real_dataset_path()

    reader = DatasetArtifactReader.from_manifest_path(manifest_path, dataset_path=dataset_path)
    dataset = reader.load()
    parquet = pd.read_parquet(dataset_path)

    assert reader.manifest_path == manifest_path.resolve()
    assert reader.dataset_path == dataset_path
    assert reader.manifest.dataset_kind == "market"
    assert reader.manifest.chunk_count == len(reader.chunk_records)
    assert reader.manifest.output_path == "/data/backtest-results/2026-06-09/e691de3d7f5b46838340a6e75da75acf/6323b5739854-alpaca-1m.parquet"
    assert not dataset.empty
    assert len(dataset) == len(parquet) == reader.manifest.total_row_count


def test_dataset_artifact_reader_falls_back_to_chunk_concatenation(tmp_path: Path) -> None:
    chunk_1 = tmp_path / "chunk-000.parquet"
    chunk_2 = tmp_path / "chunk-001.parquet"

    pd.DataFrame(
        {
            "symbol": ["AAPL"],
            "timestamp": [datetime(2026, 6, 1, tzinfo=UTC)],
            "Open": [100.0],
            "High": [101.0],
            "Low": [99.5],
            "Close": [100.5],
            "Volume": [1_000.0],
        }
    ).to_parquet(chunk_1, index=False)
    pd.DataFrame(
        {
            "symbol": ["MSFT"],
            "timestamp": [datetime(2026, 6, 1, tzinfo=UTC)],
            "Open": [200.0],
            "High": [201.0],
            "Low": [199.5],
            "Close": [200.5],
            "Volume": [2_000.0],
        }
    ).to_parquet(chunk_2, index=False)

    manifest = DatasetArtifactManifest(
        dataset_kind="market",
        dataset_id="dataset-123",
        symbols=["AAPL", "MSFT"],
        provider="alpaca",
        resolution="1d",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 1),
        output_path=str(tmp_path / "missing.parquet"),
        plan_path=str(tmp_path / "shard-plan.json"),
        primary_split_keys=["symbol"],
        fallback_split_keys=["timestamp"],
        estimated_total_work_units=2,
        shard_count=1,
        chunk_count=2,
        total_row_count=2,
        total_size_bytes=chunk_1.stat().st_size + chunk_2.stat().st_size,
        chunks=[
            DatasetChunkRecord(
                path=str(chunk_1),
                row_count=1,
                size_bytes=chunk_1.stat().st_size,
                chunk_index=0,
                split_key_values={"symbol": "AAPL"},
            ),
            DatasetChunkRecord(
                path=str(chunk_2),
                row_count=1,
                size_bytes=chunk_2.stat().st_size,
                chunk_index=1,
                split_key_values={"symbol": "MSFT"},
            ),
        ],
    )
    manifest_path = tmp_path / "dataset.manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    reader = DatasetArtifactReader.from_manifest_path(manifest_path)
    dataset = reader.load()

    assert reader.dataset_path == Path(manifest.output_path)
    assert len(dataset) == 2
    assert dataset["symbol"].tolist() == ["AAPL", "MSFT"]
    assert dataset["timestamp"].iloc[0].tzinfo is not None


def test_dataset_artifact_reader_downsamples_loaded_dataset(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.parquet"
    manifest_path = tmp_path / "dataset.manifest.json"

    dataset = pd.DataFrame(
        {
            "symbol": ["AAPL"] * 5,
            "timestamp": pd.date_range("2026-06-01", periods=5, freq="D", tz=UTC),
            "Open": [100.0, 101.0, 102.0, 103.0, 104.0],
            "High": [101.0, 102.0, 103.0, 104.0, 105.0],
            "Low": [99.0, 100.0, 101.0, 102.0, 103.0],
            "Close": [100.5, 101.5, 102.5, 103.5, 104.5],
            "Volume": [1_000.0, 1_100.0, 1_200.0, 1_300.0, 1_400.0],
        }
    )
    dataset.to_parquet(dataset_path, index=False)

    manifest = DatasetArtifactManifest(
        dataset_kind="market",
        dataset_id="dataset-123",
        symbols=["AAPL"],
        provider="alpaca",
        resolution="1d",
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
        output_path=str(dataset_path),
        plan_path=str(tmp_path / "shard-plan.json"),
        primary_split_keys=["symbol"],
        fallback_split_keys=["timestamp"],
        estimated_total_work_units=5,
        shard_count=1,
        chunk_count=1,
        total_row_count=len(dataset),
        total_size_bytes=dataset_path.stat().st_size,
        chunks=[
            DatasetChunkRecord(
                path=str(dataset_path),
                row_count=len(dataset),
                size_bytes=dataset_path.stat().st_size,
                chunk_index=0,
                split_key_values={"symbol": "AAPL"},
            ),
        ],
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    reader = DatasetArtifactReader.from_manifest_path(manifest_path)
    downsampled = reader.downsample(max_rows=3)

    assert len(downsampled) == 3
    assert downsampled["timestamp"].tolist() == [
        pd.Timestamp("2026-06-01", tz=UTC),
        pd.Timestamp("2026-06-03", tz=UTC),
        pd.Timestamp("2026-06-05", tz=UTC),
    ]
    assert downsampled["symbol"].tolist() == ["AAPL", "AAPL", "AAPL"]
