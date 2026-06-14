from __future__ import annotations

import json
import os
import shlex
import sys
import time
import shutil
from datetime import date
from pathlib import Path
from typing import Callable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import typer

from app.backtests.argo_step_errors import run_typer_app_with_argo_error_outputs
from app.backtests.argo_workflow import workflow_results_mount
from app.config.models import AlpacaDataSource, AlpacaOptionsDataSource, DataCacheConfig, YahooDataSource
from app.datasets.models import dataset_parquet_schema, normalize_dataset_parquet_frame, validate_dataset_parquet_frame
from app.datasets.sharding import (
    DatasetArtifactManifest,
    DatasetChunkRecord,
    DatasetShardPlan,
    build_dataset_shard_plan,
    dataset_slug,
    normalize_dataset_symbols,
    write_json_file,
)
from app.data.loaders import (
    build_alpaca_data_feed_with_cache,
    build_alpaca_options_data_feed_with_cache,
    build_yahoo_data_feed_with_cache,
)
from app.script_logging import emit_info, emit_terminal_command, emit_warning
from app.backtests.argo_progress import (
    ARGO_PROGRESS_TOTAL,
    ThrottledProgressWriter,
    parse_argo_progress,
    progress_fraction,
    resolve_progress_file,
)

app = typer.Typer(add_completion=False, no_args_is_help=True)

_DATASET_PLAN_FILENAME = "shard-plan.json"
_SHARD_PROGRESS_FILENAME = "argo-progress.txt"
_COMBINE_PROGRESS_FILENAME = "combine-progress.txt"
_DEFAULT_AGGREGATE_POLL_INTERVAL_SECONDS = 2.0


def _write_text(path: str | None, text: str) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _terminal_command(argv: list[str]) -> str:
    return " ".join(shlex.quote(arg) for arg in argv)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(1, value)


def _frame_with_timestamp_column(frame: pd.DataFrame) -> pd.DataFrame:
    if "timestamp" in frame.columns:
        return frame

    if "datetime" in frame.columns:
        out = frame.rename(columns={"datetime": "timestamp"}).copy()
        if "index" in out.columns:
            out = out.drop(columns=["index"])
        return out

    out = frame.reset_index()
    if "timestamp" in out.columns:
        return out

    if "index" in out.columns:
        return out.rename(columns={"index": "timestamp"})

    index_columns = [column for column in out.columns if column not in frame.columns]
    if index_columns:
        return out.rename(columns={index_columns[0]: "timestamp"})
    return out


def _dataset_parquet_table(frame: pd.DataFrame) -> pa.Table:
    normalized_frame = normalize_dataset_parquet_frame(frame)
    validate_dataset_parquet_frame(normalized_frame)
    return pa.Table.from_pandas(normalized_frame, schema=dataset_parquet_schema(), preserve_index=False)


def _log(message: str) -> None:
    emit_info("dataset-download", message, script="datasets_download_argo")


def _is_missing_alpaca_symbol_data_error(exc: RuntimeError) -> bool:
    message = str(exc)
    return message.startswith("No Alpaca data found for symbol ") or message.startswith(
        "No Alpaca options data found for symbol "
    )


def _progress_file_for_shard(output_dir: str | Path) -> Path:
    return Path(output_dir) / _SHARD_PROGRESS_FILENAME


def _progress_file_for_combine(output_dir: str | Path) -> Path:
    return Path(output_dir) / _COMBINE_PROGRESS_FILENAME


def _read_progress_fraction(path: Path) -> float:
    if not path.exists():
        return 0.0
    try:
        parsed = parse_argo_progress(path.read_text(encoding="utf-8"))
    except OSError:
        return 0.0
    if parsed is None:
        return 0.0
    completed, total = parsed
    return progress_fraction(completed, total)


def _shard_progress_fraction(shard: DatasetShardPlan, *, final_complete: bool) -> float:
    progress_path = _progress_file_for_shard(shard.output_dir)
    if progress_path.exists():
        return _read_progress_fraction(progress_path)
    return 1.0 if final_complete else 0.0


def _aggregate_progress_pct(shard_plan: DatasetShardPlan) -> int:
    total_units = float(max(1, shard_plan.combine_weight_units))
    completed_units = 0.0
    final_complete = _aggregate_progress_complete(shard_plan)

    for shard in shard_plan.shards:
        shard_progress = _shard_progress_fraction(shard, final_complete=final_complete)
        total_units += float(max(1, shard.work_units))
        completed_units += shard_progress * float(max(1, shard.work_units))

    combine_progress = _read_progress_fraction(_progress_file_for_combine(shard_plan.output_dir))
    if combine_progress > 0.0:
        completed_units += combine_progress * float(max(1, shard_plan.combine_weight_units))
    elif Path(shard_plan.dataset_output_path).exists() and Path(shard_plan.dataset_manifest_path).exists():
        completed_units += float(max(1, shard_plan.combine_weight_units))

    if total_units <= 0:
        return 0
    return max(0, min(ARGO_PROGRESS_TOTAL, round((completed_units / total_units) * ARGO_PROGRESS_TOTAL)))


def _aggregate_progress_complete(shard_plan: DatasetShardPlan) -> bool:
    final_paths = [Path(shard_plan.dataset_output_path), Path(shard_plan.dataset_manifest_path)]
    if shard_plan.options_enabled and shard_plan.options_output_path and shard_plan.options_manifest_path:
        final_paths.extend([Path(shard_plan.options_output_path), Path(shard_plan.options_manifest_path)])
    return all(path.exists() for path in final_paths)


def _canonical_dataset_paths(
    *,
    symbols: list[str],
    provider: str,
    resolution: str,
    output_dir: Path,
    options_enabled: bool,
) -> tuple[Path, Path, Path | None, Path | None]:
    slug = dataset_slug(symbols)
    provider_normalized = provider.strip().lower()
    market_parquet = output_dir / f"{slug}-{provider_normalized}-{resolution}.parquet"
    market_manifest = output_dir / f"{slug}-{provider_normalized}-{resolution}.manifest.json"
    if not options_enabled:
        return market_parquet, market_manifest, None, None
    options_parquet = output_dir / f"{slug}-alpaca-options-{resolution}.parquet"
    options_manifest = output_dir / f"{slug}-alpaca-options-{resolution}.manifest.json"
    return market_parquet, market_manifest, options_parquet, options_manifest


def _write_parquet_from_frames(
    *,
    parquet_path: Path,
    frame_loader: Callable[[str], pd.DataFrame],
    symbols: list[str],
    frame_label: str = "dataset",
) -> int:
    temp_path = parquet_path.with_suffix(parquet_path.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()

    writer: pq.ParquetWriter | None = None
    row_count = 0
    success = False
    try:
        for symbol in symbols:
            frame = frame_loader(symbol)
            table = _dataset_parquet_table(frame)
            if writer is None:
                writer = pq.ParquetWriter(temp_path, table.schema)
            writer.write_table(table)
            row_count += len(frame)
        if writer is None:
            raise RuntimeError(f"No {frame_label} frames were written")
        success = True
        return row_count
    finally:
        if writer is not None:
            writer.close()
        if success:
            temp_path.replace(parquet_path)
        elif temp_path.exists():
            temp_path.unlink()


def _dataset_manifest(
    *,
    dataset_kind: str,
    dataset_id: str,
    symbols: list[str],
    provider: str,
    resolution: str,
    start_date: date,
    end_date: date,
    output_path: Path,
    plan_path: str,
    row_count: int,
    total_size_bytes: int,
) -> DatasetArtifactManifest:
    return DatasetArtifactManifest(
        dataset_kind=dataset_kind,  # type: ignore[arg-type]
        dataset_id=dataset_id,
        symbols=symbols,
        provider=provider,
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        output_path=str(output_path),
        plan_path=plan_path,
        primary_split_keys=["symbol"],
        fallback_split_keys=["timestamp"],
        estimated_total_work_units=max(0, row_count),
        shard_count=1,
        chunk_count=1,
        total_row_count=row_count,
        total_size_bytes=total_size_bytes,
        chunks=[
            DatasetChunkRecord(
                path=str(output_path),
                row_count=row_count,
                size_bytes=total_size_bytes,
                chunk_index=0,
                split_key_values={"symbol": symbols[0]},
            )
        ],
    )


def _write_shard_parquets(
    *,
    dataset_id: str,
    provider: str,
    resolution: str,
    start_date: date,
    end_date: date,
    market_parquet_path: Path,
    market_manifest_path: Path,
    options_parquet_path: Path | None,
    options_manifest_path: Path | None,
    symbols: list[str],
    market_frame_loader: Callable[[str], pd.DataFrame],
    options_frame_loader: Callable[[str], pd.DataFrame] | None,
    progress_total_units: int,
    progress_symbol_units: int,
    progress_file: str | None,
    shard_label: str,
) -> tuple[int, int | None]:
    progress_path = resolve_progress_file(progress_file)
    progress_writer = ThrottledProgressWriter(progress_path) if progress_path is not None else None
    if progress_writer is not None:
        progress_writer.write_immediate(0)

    market_tmp = market_parquet_path.with_suffix(market_parquet_path.suffix + ".tmp")
    options_tmp = options_parquet_path.with_suffix(options_parquet_path.suffix + ".tmp") if options_parquet_path else None
    for path in [market_tmp, options_tmp]:
        if path is not None and path.exists():
            path.unlink()

    market_writer: pq.ParquetWriter | None = None
    options_writer: pq.ParquetWriter | None = None
    market_rows = 0
    options_rows = 0
    completed_units = 0
    success = False
    symbol_step_units = max(1, progress_symbol_units)
    if options_frame_loader is not None:
        symbol_step_units = max(1, progress_symbol_units // 2)

    try:
        for symbol in symbols:
            _log(f"Loading market data for {shard_label}:{symbol}")
            try:
                market_frame = market_frame_loader(symbol)
            except RuntimeError as exc:
                if not _is_missing_alpaca_symbol_data_error(exc):
                    raise
                emit_warning(
                    "dataset-download",
                    f"Skipping {shard_label}:{symbol} after missing Alpaca market data",
                    script="datasets_download_argo",
                    error=str(exc),
                )
                completed_units += max(1, progress_symbol_units)
                if progress_writer is not None:
                    progress_writer.write(min(progress_total_units, completed_units))
                continue
            market_frame = _frame_with_timestamp_column(market_frame)
            market_frame["symbol"] = symbol
            market_table = _dataset_parquet_table(market_frame)
            if market_writer is None:
                market_writer = pq.ParquetWriter(market_tmp, market_table.schema)
            market_writer.write_table(market_table)
            market_rows += len(market_frame)
            completed_units += symbol_step_units
            if progress_writer is not None:
                progress_writer.write(min(progress_total_units, completed_units))

            if options_frame_loader is None or options_parquet_path is None:
                continue

            _log(f"Loading options data for {shard_label}:{symbol}")
            try:
                options_frame = options_frame_loader(symbol)
            except RuntimeError as exc:
                if not _is_missing_alpaca_symbol_data_error(exc):
                    raise
                emit_warning(
                    "dataset-download",
                    f"Skipping options for {shard_label}:{symbol} after missing Alpaca options data",
                    script="datasets_download_argo",
                    error=str(exc),
                )
                completed_units += symbol_step_units
                if progress_writer is not None:
                    progress_writer.write(min(progress_total_units, completed_units))
                continue
            options_frame = _frame_with_timestamp_column(options_frame)
            options_frame["symbol"] = symbol
            options_table = _dataset_parquet_table(options_frame)
            if options_writer is None:
                options_writer = pq.ParquetWriter(options_tmp, options_table.schema)  # type: ignore[arg-type]
            options_writer.write_table(options_table)
            options_rows += len(options_frame)
            completed_units += symbol_step_units
            if progress_writer is not None:
                progress_writer.write(min(progress_total_units, completed_units))

        if market_writer is None:
            raise RuntimeError(f"No market data frames were written for {shard_label}")
        if options_frame_loader is not None and options_parquet_path is not None and options_writer is None:
            raise RuntimeError(f"No options data frames were written for {shard_label}")

        market_writer.close()
        market_writer = None
        if options_writer is not None:
            options_writer.close()
            options_writer = None
        success = True
        return market_rows, options_rows if options_parquet_path is not None else None
    finally:
        if market_writer is not None:
            market_writer.close()
        if options_writer is not None:
            options_writer.close()
        if market_tmp.exists():
            market_tmp.replace(market_parquet_path)
        if options_tmp is not None and options_tmp.exists():
            options_tmp.replace(options_parquet_path)  # type: ignore[arg-type]

        market_size_bytes = market_parquet_path.stat().st_size if market_parquet_path.exists() else 0
        write_json_file(
            market_manifest_path,
            _dataset_manifest(
                dataset_kind="market",
                dataset_id=dataset_id,
                symbols=symbols,
                provider=provider,
                resolution=resolution,
                start_date=start_date,
                end_date=end_date,
                output_path=market_parquet_path,
                plan_path="",
                row_count=market_rows,
                total_size_bytes=market_size_bytes,
            ),
        )

        if options_manifest_path is not None and options_parquet_path is not None and options_parquet_path.exists():
            options_size_bytes = options_parquet_path.stat().st_size
            write_json_file(
                options_manifest_path,
                _dataset_manifest(
                    dataset_kind="options",
                    dataset_id=dataset_id,
                    symbols=symbols,
                    provider=provider,
                    resolution=resolution,
                    start_date=start_date,
                    end_date=end_date,
                    output_path=options_parquet_path,
                    plan_path="",
                    row_count=options_rows,
                    total_size_bytes=options_size_bytes,
                ),
            )
        if progress_writer is not None and success:
            progress_writer.write_immediate(progress_total_units)


def _legacy_download_bundle(
    *,
    symbol: str,
    provider: str,
    resolution: str,
    start_date: str,
    end_date: str,
    options_enabled: bool,
    options_feed: str,
    output_dir: str,
    dataset_path_out: str | None,
    manifest_path_out: str | None,
    options_dataset_path_out: str | None,
    options_manifest_path_out: str | None,
) -> None:
    from datetime import date as _date

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    symbols_normalized = normalize_dataset_symbols(symbol.split(","))
    if not symbols_normalized:
        raise ValueError("At least one symbol must be provided")

    provider_normalized = provider.strip().lower()
    start = _date.fromisoformat(start_date)
    end = _date.fromisoformat(end_date)
    cache_config = DataCacheConfig(directory=str(out_dir / ".cache"))

    _log(
        "Starting dataset download: "
        f"symbols={','.join(symbols_normalized)} provider={provider_normalized} "
        f"resolution={resolution} start_date={start.isoformat()} end_date={end.isoformat()}"
    )
    _log(f"Writing artifacts to {out_dir}")
    _log(f"Using cache directory {cache_config.directory}")

    def _load_frame(symbol_normalized: str) -> pd.DataFrame:
        if provider_normalized == "alpaca":
            _log(f"Loading Alpaca data feed for {symbol_normalized}")
            frame, _ = build_alpaca_data_feed_with_cache(
                AlpacaDataSource(type="alpaca", symbol=symbol_normalized, interval=resolution, feed="iex"),
                start,
                end,
                cache_config,
            )
        elif provider_normalized == "yahoo":
            _log(f"Loading Yahoo data feed for {symbol_normalized}")
            frame, _ = build_yahoo_data_feed_with_cache(
                YahooDataSource(type="yahoo", symbol=symbol_normalized, interval=resolution),
                start,
                end,
                cache_config,
            )
        else:
            raise ValueError("provider must be alpaca or yahoo")
        frame = _frame_with_timestamp_column(frame)
        frame["symbol"] = symbol_normalized
        return frame

    options_parquet_path: Path | None = None
    options_manifest: Path | None = None
    if options_enabled:
        _log("Loading Alpaca options data feed")

        def _load_options_frame(symbol_normalized: str) -> pd.DataFrame:
            options_frame, _ = build_alpaca_options_data_feed_with_cache(
                AlpacaOptionsDataSource(
                    type="alpaca-options",
                    symbol=symbol_normalized,
                    interval=resolution,
                    feed=options_feed,  # type: ignore[arg-type]
                ),
                start,
                end,
                cache_config,
            )
            options_frame = _frame_with_timestamp_column(options_frame)
            options_frame["symbol"] = symbol_normalized
            return options_frame

        options_slug = dataset_slug(symbols_normalized)
        options_parquet_path = out_dir / f"{options_slug}-alpaca-options-{resolution}.parquet"
        options_manifest = out_dir / f"{options_slug}-alpaca-options-{resolution}.manifest.json"
        _log(f"Saving options parquet to {options_parquet_path}")
        options_row_count = _write_parquet_from_frames(
            parquet_path=options_parquet_path,
            frame_loader=_load_options_frame,
            symbols=symbols_normalized,
            frame_label="options",
        )
        _log(f"Saving options manifest to {options_manifest}")
        options_manifest.write_text(
            _dataset_manifest(
                dataset_kind="options",
                dataset_id=out_dir.name or "dataset",
                symbols=symbols_normalized,
                provider="alpaca-options",
                resolution=resolution,
                start_date=start,
                end_date=end,
                output_path=options_parquet_path,
                plan_path="",
                row_count=options_row_count,
                total_size_bytes=options_parquet_path.stat().st_size,
            ).model_dump_json(indent=2),
            encoding="utf-8",
        )

    _log("Saving dataset parquet")
    dataset_slug_value = dataset_slug(symbols_normalized)
    parquet_path = out_dir / f"{dataset_slug_value}-{provider_normalized}-{resolution}.parquet"
    manifest_path = out_dir / f"{dataset_slug_value}-{provider_normalized}-{resolution}.manifest.json"
    row_count = _write_parquet_from_frames(
        parquet_path=parquet_path,
        frame_loader=_load_frame,
        symbols=symbols_normalized,
        frame_label="dataset",
    )
    _log(f"Downloaded frame with {row_count} rows")
    _log(f"Saving manifest to {manifest_path}")
    manifest_path.write_text(
        _dataset_manifest(
            dataset_kind="market",
            dataset_id=out_dir.name or "dataset",
            symbols=symbols_normalized,
            provider=provider_normalized,
            resolution=resolution,
            start_date=start,
            end_date=end,
            output_path=parquet_path,
            plan_path="",
            row_count=row_count,
            total_size_bytes=parquet_path.stat().st_size,
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )

    _write_text(dataset_path_out, str(parquet_path))
    _write_text(manifest_path_out, str(manifest_path))
    _write_text(options_dataset_path_out, str(options_parquet_path) if options_parquet_path else "")
    _write_text(options_manifest_path_out, str(options_manifest) if options_manifest else "")
    _log("Dataset download complete")
    _log(f"Dataset path: {parquet_path}")
    _log(f"Manifest path: {manifest_path}")
    if options_parquet_path and options_manifest:
        _log(f"Options dataset path: {options_parquet_path}")
        _log(f"Options manifest path: {options_manifest}")


def _source_parquet_path(shard: dict[str, object], dataset_kind: str) -> Path:
    key = "market_parquet_path" if dataset_kind == "market" else "options_parquet_path"
    raw = shard.get(key)
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"Shard is missing {key}")
    return Path(raw)


def _combine_dataset_kind(
    *,
    shard_plan: DatasetShardPlan,
    dataset_kind: str,
    final_output_path: Path,
    final_manifest_path: Path,
    progress_file: str | None,
    max_chunk_size_bytes: int,
) -> DatasetArtifactManifest | None:
    if dataset_kind == "options" and not shard_plan.options_enabled:
        return None

    source_key = "market_parquet_path" if dataset_kind == "market" else "options_parquet_path"
    chunk_root = final_output_path.parent / "chunks" / dataset_kind
    chunk_root.mkdir(parents=True, exist_ok=True)

    temp_output = final_output_path.with_suffix(final_output_path.suffix + ".tmp")
    if temp_output.exists():
        temp_output.unlink()

    progress_path = resolve_progress_file(progress_file)
    progress_writer = ThrottledProgressWriter(progress_path) if progress_path is not None else None
    if progress_writer is not None:
        progress_writer.write_immediate(0)

    canonical_writer: pq.ParquetWriter | None = None
    manifest_chunks: list[DatasetChunkRecord] = []

    active_chunk_writer: pq.ParquetWriter | None = None
    active_chunk_temp_path: Path | None = None
    active_chunk_final_path: Path | None = None
    active_chunk_row_count: int = 0
    active_chunk_symbols: set[str] = set()
    active_chunk_nbytes: int = 0
    chunk_index: int = 0

    def _close_active_chunk() -> None:
        nonlocal active_chunk_writer, active_chunk_temp_path, active_chunk_final_path
        nonlocal active_chunk_row_count, active_chunk_symbols, active_chunk_nbytes, chunk_index
        if active_chunk_writer is not None and active_chunk_temp_path is not None and active_chunk_final_path is not None:
            active_chunk_writer.close()
            active_chunk_temp_path.replace(active_chunk_final_path)
            manifest_chunks.append(
                DatasetChunkRecord(
                    path=str(active_chunk_final_path),
                    row_count=active_chunk_row_count,
                    size_bytes=active_chunk_final_path.stat().st_size,
                    chunk_index=chunk_index,
                    symbols=sorted(active_chunk_symbols),
                )
            )
            chunk_index += 1
        active_chunk_writer = None
        active_chunk_temp_path = None
        active_chunk_final_path = None
        active_chunk_row_count = 0
        active_chunk_nbytes = 0
        active_chunk_symbols.clear()

    total_rows = 0
    total_size_bytes = 0
    completed_shards = 0
    skipped_shards: list[str] = []

    try:
        for shard in shard_plan.shards:
            source_path = _source_parquet_path(shard.model_dump(), dataset_kind)
            if not source_path.exists():
                skipped_shards.append(str(source_path))
                emit_warning(
                    "missing-shard-parquet",
                    f"Skipping missing {dataset_kind} shard parquet",
                    script="datasets_download_argo",
                    source_path=str(source_path),
                    shard_id=shard.shard_id,
                )
                continue
            parquet_file = pq.ParquetFile(source_path)
            for batch in parquet_file.iter_batches(batch_size=4096):
                table = pa.Table.from_batches([batch])
                if canonical_writer is None:
                    canonical_writer = pq.ParquetWriter(temp_output, table.schema)
                canonical_writer.write_table(table)
                total_rows += table.num_rows

                frame = batch.to_pandas()
                if "symbol" not in frame.columns:
                    raise ValueError(f"Shard parquet missing symbol column: {source_path}")
                
                if active_chunk_writer is None:
                    active_chunk_final_path = chunk_root / f"part_{chunk_index:03d}.parquet"
                    active_chunk_temp_path = active_chunk_final_path.with_suffix(".tmp")
                    if active_chunk_temp_path.exists():
                        active_chunk_temp_path.unlink()
                    active_chunk_writer = pq.ParquetWriter(active_chunk_temp_path, table.schema)
                
                active_chunk_writer.write_table(table)
                active_chunk_row_count += table.num_rows
                active_chunk_symbols.update(str(s).strip().upper() for s in frame["symbol"].unique() if pd.notna(s))
                active_chunk_nbytes += table.nbytes

                if active_chunk_nbytes >= max_chunk_size_bytes:
                    _close_active_chunk()

            completed_shards += 1
            if progress_writer is not None:
                progress_writer.write(completed_shards)

        if canonical_writer is None:
            if skipped_shards:
                raise RuntimeError(
                    f"No rows were combined for {dataset_kind}; skipped missing shard parquets: "
                    f"{', '.join(skipped_shards)}"
                )
            raise RuntimeError(f"No rows were combined for {dataset_kind}")

        _close_active_chunk()

        canonical_writer.close()
        canonical_writer = None
        temp_output.replace(final_output_path)
        total_size_bytes = sum(chunk.size_bytes for chunk in manifest_chunks)
        manifest = DatasetArtifactManifest(
            dataset_kind=dataset_kind,  # type: ignore[arg-type]
            dataset_id=shard_plan.dataset_id,
            symbols=shard_plan.symbols,
            provider=shard_plan.provider,
            resolution=shard_plan.resolution,
            start_date=shard_plan.start_date,
            end_date=shard_plan.end_date,
            output_path=str(final_output_path),
            plan_path=shard_plan.plan_path,
            primary_split_keys=[],
            fallback_split_keys=shard_plan.fallback_split_keys,
            estimated_total_work_units=shard_plan.estimated_total_work_units,
            shard_count=shard_plan.shard_count,
            chunk_count=len(manifest_chunks),
            total_row_count=total_rows,
            total_size_bytes=total_size_bytes,
            chunks=manifest_chunks,
        )
        write_json_file(final_manifest_path, manifest)
        return manifest
    finally:
        if canonical_writer is not None:
            canonical_writer.close()
        if temp_output.exists():
            temp_output.unlink()
        if progress_writer is not None:
            progress_writer.write_immediate(max(1, completed_shards))


def _cleanup_shard_artifacts(shard_plan: DatasetShardPlan) -> None:
    shards_root = Path(shard_plan.output_dir) / "shards"
    for shard in shard_plan.shards:
        shard_dir = Path(shard.output_dir)
        if shard_dir.exists():
            shutil.rmtree(shard_dir)
    if shards_root.exists() and not any(shards_root.iterdir()):
        shards_root.rmdir()


@app.command(help="Argo-safe dataset downloader that writes parquet artifacts to shared storage.")
def main(
    symbol: str = typer.Option(..., "--symbol", "--symbols"),
    provider: str = typer.Option(..., "--provider"),
    resolution: str = typer.Option(..., "--resolution"),
    start_date: str = typer.Option(..., "--start-date"),
    end_date: str = typer.Option(..., "--end-date"),
    options_enabled: bool = typer.Option(False, "--options-enabled/--no-options-enabled"),
    options_feed: str = typer.Option("indicative", "--options-feed"),
    output_dir: str = typer.Option(..., "--output-dir"),
    terminal_command_out: str | None = typer.Option(None, "--terminal-command-out"),
    dataset_path_out: str | None = typer.Option(None, "--dataset-path-out"),
    manifest_path_out: str | None = typer.Option(None, "--manifest-path-out"),
    options_dataset_path_out: str | None = typer.Option(None, "--options-dataset-path-out"),
    options_manifest_path_out: str | None = typer.Option(None, "--options-manifest-path-out"),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="datasets_download_argo")
    _write_text(dataset_path_out, "")
    _write_text(manifest_path_out, "")
    _write_text(options_dataset_path_out, "")
    _write_text(options_manifest_path_out, "")
    _legacy_download_bundle(
        symbol=symbol,
        provider=provider,
        resolution=resolution,
        start_date=start_date,
        end_date=end_date,
        options_enabled=options_enabled,
        options_feed=options_feed,
        output_dir=output_dir,
        dataset_path_out=dataset_path_out,
        manifest_path_out=manifest_path_out,
        options_dataset_path_out=options_dataset_path_out,
        options_manifest_path_out=options_manifest_path_out,
    )


@app.command("plan-shards", help="Plan dataset download shards and write the shard manifest.")
def plan_shards_command(
    symbol: str = typer.Option(..., "--symbol", "--symbols"),
    provider: str = typer.Option(..., "--provider"),
    resolution: str = typer.Option(..., "--resolution"),
    start_date: str = typer.Option(..., "--start-date"),
    end_date: str = typer.Option(..., "--end-date"),
    options_enabled: bool = typer.Option(False, "--options-enabled/--no-options-enabled"),
    options_feed: str = typer.Option("indicative", "--options-feed"),
    output_dir: str = typer.Option(..., "--output-dir"),
    plan_path_out: str = typer.Option("/tmp/plan-path.txt", "--plan-path-out"),
    work_dir_out: str = typer.Option("/tmp/work-dir.txt", "--work-dir-out"),
    shards_param_out: str = typer.Option("/tmp/shards-param.json", "--shards-param-out"),
    terminal_command_out: str = typer.Option("/tmp/terminal-command.txt", "--terminal-command-out"),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="datasets_download_argo")

    symbols = normalize_dataset_symbols(symbol.split(","))
    if not symbols:
        raise ValueError("At least one symbol must be provided")

    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    dataset_id = out_dir.name or "dataset"
    plan = build_dataset_shard_plan(
        dataset_id=dataset_id,
        symbols=symbols,
        provider=provider,
        resolution=resolution,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date),
        options_enabled=options_enabled,
        options_feed=options_feed,
        output_dir=out_dir,
        max_shards=_env_int("DATASET_MAX_SHARDS", 8),
        max_pods=_env_int("DATASET_MAX_PODS", 4),
        target_work_units=_env_int("DATASET_TARGET_WORK_UNITS", 5_000),
    )
    plan_path = Path(plan.plan_path)
    write_json_file(plan_path, plan)
    _write_text(plan_path_out, str(plan_path))
    _write_text(work_dir_out, str(out_dir))
    _write_text(shards_param_out, json.dumps([shard.model_dump() for shard in plan.shards], indent=2))


@app.command("download-shard", help="Download a single dataset shard into shared storage.")
def download_shard_command(
    shard_id: str = typer.Option(..., "--shard-id"),
    symbols: str = typer.Option(..., "--symbols"),
    provider: str = typer.Option(..., "--provider"),
    resolution: str = typer.Option(..., "--resolution"),
    start_date: str = typer.Option(..., "--start-date"),
    end_date: str = typer.Option(..., "--end-date"),
    options_enabled: bool = typer.Option(False, "--options-enabled/--no-options-enabled"),
    options_feed: str = typer.Option("indicative", "--options-feed"),
    output_dir: str = typer.Option(..., "--output-dir"),
    progress_total_units: int = typer.Option(..., "--progress-total-units"),
    progress_symbol_units: int = typer.Option(..., "--progress-symbol-units"),
    terminal_command_out: str = typer.Option("/tmp/terminal-command.txt", "--terminal-command-out"),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="datasets_download_argo")

    shard_symbols = normalize_dataset_symbols(symbols.split(","))
    if not shard_symbols:
        raise ValueError("At least one symbol must be provided")

    shard_dir = Path(output_dir).resolve()
    shard_dir.mkdir(parents=True, exist_ok=True)
    market_parquet_path = shard_dir / "market.parquet"
    market_manifest_path = shard_dir / "market.manifest.json"
    options_parquet_path = shard_dir / "options.parquet" if options_enabled else None
    options_manifest_path = shard_dir / "options.manifest.json" if options_enabled else None

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    cache_config = DataCacheConfig(directory=str(shard_dir / ".cache"))
    provider_normalized = provider.strip().lower()

    _log(f"Starting shard {shard_id}: symbols={','.join(shard_symbols)} output_dir={shard_dir}")

    def _load_market_frame(symbol_normalized: str) -> pd.DataFrame:
        if provider_normalized == "alpaca":
            frame, _ = build_alpaca_data_feed_with_cache(
                AlpacaDataSource(type="alpaca", symbol=symbol_normalized, interval=resolution, feed="iex"),
                start,
                end,
                cache_config,
            )
        elif provider_normalized == "yahoo":
            frame, _ = build_yahoo_data_feed_with_cache(
                YahooDataSource(type="yahoo", symbol=symbol_normalized, interval=resolution),
                start,
                end,
                cache_config,
            )
        else:
            raise ValueError("provider must be alpaca or yahoo")
        return frame

    options_loader: Callable[[str], pd.DataFrame] | None = None
    if options_enabled:
        if provider_normalized != "alpaca":
            raise ValueError("options downloads are only supported for the alpaca provider")

        def _load_options_frame(symbol_normalized: str) -> pd.DataFrame:
            options_frame, _ = build_alpaca_options_data_feed_with_cache(
                AlpacaOptionsDataSource(
                    type="alpaca-options",
                    symbol=symbol_normalized,
                    interval=resolution,
                    feed=options_feed,  # type: ignore[arg-type]
                ),
                start,
                end,
                cache_config,
            )
            return options_frame

        options_loader = _load_options_frame

    _write_shard_parquets(
        dataset_id=shard_id,
        provider=provider_normalized,
        resolution=resolution,
        start_date=start,
        end_date=end,
        market_parquet_path=market_parquet_path,
        market_manifest_path=market_manifest_path,
        options_parquet_path=options_parquet_path,
        options_manifest_path=options_manifest_path,
        symbols=shard_symbols,
        market_frame_loader=_load_market_frame,
        options_frame_loader=options_loader,
        progress_total_units=progress_total_units,
        progress_symbol_units=progress_symbol_units,
        progress_file=str(_progress_file_for_shard(shard_dir)),
        shard_label=shard_id,
    )
    _log(f"Completed shard {shard_id}")


@app.command("aggregate-progress", help="Aggregate shard progress into a workflow-level progress stream.")
def aggregate_progress_command(
    plan_path: str = typer.Option(..., "--plan-path"),
    poll_interval_seconds: float = typer.Option(
        _DEFAULT_AGGREGATE_POLL_INTERVAL_SECONDS,
        "--poll-interval-seconds",
    ),
    terminal_command_out: str = typer.Option("/tmp/terminal-command.txt", "--terminal-command-out"),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="datasets_download_argo")

    shard_plan = DatasetShardPlan.model_validate_json(Path(plan_path).read_text(encoding="utf-8"))
    progress_path = resolve_progress_file(None)
    progress_writer = ThrottledProgressWriter(progress_path) if progress_path is not None else None
    if progress_writer is not None:
        progress_writer.write_immediate(0)

    interval = max(0.1, float(poll_interval_seconds))
    while True:
        aggregate_pct = _aggregate_progress_pct(shard_plan)
        if progress_writer is not None:
            progress_writer.write(aggregate_pct)
        if aggregate_pct >= ARGO_PROGRESS_TOTAL and _aggregate_progress_complete(shard_plan):
            if progress_writer is not None:
                progress_writer.write_immediate(ARGO_PROGRESS_TOTAL)
            return
        time.sleep(interval)


@app.command("combine-shards", help="Combine shard parquet files into the final dataset parquet(s).")
def combine_shards_command(
    plan_path: str = typer.Option(..., "--plan-path"),
    dataset_path_out: str = typer.Option("/tmp/dataset-path.txt", "--dataset-path-out"),
    manifest_path_out: str = typer.Option("/tmp/manifest-path.txt", "--manifest-path-out"),
    options_dataset_path_out: str = typer.Option("/tmp/options-dataset-path.txt", "--options-dataset-path-out"),
    options_manifest_path_out: str = typer.Option("/tmp/options-manifest-path.txt", "--options-manifest-path-out"),
    max_chunk_size_bytes: int = typer.Option(20 * 1024 * 1024, "--max-chunk-size-bytes", help="Maximum chunk size in bytes"),
    terminal_command_out: str = typer.Option("/tmp/terminal-command.txt", "--terminal-command-out"),
) -> None:
    emit_terminal_command(sys.argv, terminal_command_out=terminal_command_out, script="datasets_download_argo")
    _write_text(dataset_path_out, "")
    _write_text(manifest_path_out, "")
    _write_text(options_dataset_path_out, "")
    _write_text(options_manifest_path_out, "")

    shard_plan = DatasetShardPlan.model_validate_json(Path(plan_path).read_text(encoding="utf-8"))
    progress_file = str(_progress_file_for_combine(shard_plan.output_dir))
    market_manifest = _combine_dataset_kind(
        shard_plan=shard_plan,
        dataset_kind="market",
        final_output_path=Path(shard_plan.dataset_output_path),
        final_manifest_path=Path(shard_plan.dataset_manifest_path),
        progress_file=progress_file,
        max_chunk_size_bytes=max_chunk_size_bytes,
    )
    if market_manifest is None:
        raise RuntimeError("Market dataset combine unexpectedly returned no manifest")

    _write_text(dataset_path_out, str(shard_plan.dataset_output_path))
    _write_text(manifest_path_out, str(shard_plan.dataset_manifest_path))

    if shard_plan.options_enabled and shard_plan.options_output_path and shard_plan.options_manifest_path:
        options_manifest = _combine_dataset_kind(
            shard_plan=shard_plan,
            dataset_kind="options",
            final_output_path=Path(shard_plan.options_output_path),
            final_manifest_path=Path(shard_plan.options_manifest_path),
            progress_file=progress_file,
            max_chunk_size_bytes=max_chunk_size_bytes,
        )
        if options_manifest is not None:
            _write_text(options_dataset_path_out, str(shard_plan.options_output_path))
            _write_text(options_manifest_path_out, str(shard_plan.options_manifest_path))

    _cleanup_shard_artifacts(shard_plan)


if __name__ == "__main__":
    run_typer_app_with_argo_error_outputs(app)
