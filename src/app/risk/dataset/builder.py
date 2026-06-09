from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import tempfile

import pandas as pd
import yaml

from app.backtests.artifacts import (
    default_artifact_paths,
    hydrate_report_from_artifacts,
    resolve_results_root,
)
from app.config.models import DataCacheConfig
from app.output.models import BacktestReport, FeatureSnapshotRecord, OutcomeLabelRecord
from app.risk.data.bars import BarStore, bar_index_at_or_before
from app.risk.data.report_loader import load_candidates_from_reports
from app.risk.features.assemble import build_feature_snapshot
from app.risk.labels.path_labels import label_long_candidate
from app.risk.models import EnrichedCandidate, RiskDatasetChunkRecord, RiskDatasetConfig, RiskDatasetManifest


def load_risk_dataset_config(path: Path | None) -> RiskDatasetConfig:
    if path is None or not path.exists():
        return RiskDatasetConfig()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    risk_dataset = raw.get("risk_dataset", {})
    labels = raw.get("labels", {})
    features = raw.get("features", {})
    data_cache = raw.get("data_cache", {})
    return RiskDatasetConfig(
        dataset_version=str(risk_dataset.get("dataset_version", "risk_dataset_v1")),
        label_version=str(risk_dataset.get("label_version", "labels_v1")),
        feature_version=str(risk_dataset.get("feature_version", "features_v1")),
        ambiguous_intrabar_policy=labels.get("ambiguous_intrabar_policy", "assume_stop_first"),
        min_history_bars=int(features.get("min_history_bars", 60)),
        lookback_bars=int(features.get("lookback_bars", 60)),
        winsorize_quantiles=list(features.get("winsorize_quantiles", [0.01, 0.99])),
        vol_percentile_window=int(features.get("vol_percentile_window", 60)),
        include_index_features=bool(features.get("include_index_features", True)),
        default_benchmark_symbol=str(features.get("default_benchmark_symbol", "SPY")),
        cache_directory=str(data_cache.get("directory", ".cache/backtest-data")),
        cache_enabled=bool(data_cache.get("enabled", True)),
        max_parquet_file_size_bytes=int(
            risk_dataset.get("max_parquet_file_size_bytes", 10 * 1024 * 1024)
        ),
        parquet_split_primary_keys=list(risk_dataset.get("parquet_split_primary_keys", ["symbol"])),
        parquet_split_fallback_keys=list(
            risk_dataset.get("parquet_split_fallback_keys", ["run_id", "candidate_id"])
        ),
    )


def _config_hash(config: RiskDatasetConfig) -> str:
    payload = config.model_dump()
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _candidate_row(candidate: EnrichedCandidate) -> dict[str, Any]:
    row = candidate.model_dump(mode="json")
    metadata = row.pop("metadata", {})
    if isinstance(metadata, dict):
        for key, value in metadata.items():
            if isinstance(value, (bool, int, float, str)) or value is None:
                row[f"meta_{key}"] = value
    return row


def _label_row(label: OutcomeLabelRecord) -> dict[str, Any]:
    return label.model_dump(mode="json")


def _feature_row(snapshot: FeatureSnapshotRecord) -> dict[str, Any]:
    base = snapshot.model_dump(mode="json")
    metadata_features = base.pop("metadata_features", {})
    for key, value in metadata_features.items():
        base[key] = value
    return base


@dataclass(frozen=True)
class _DatasetChunkPlan:
    frame: pd.DataFrame
    split_key_values: dict[str, str | None]


def _config_split_key_groups(config: RiskDatasetConfig) -> list[tuple[str, ...]]:
    groups: list[tuple[str, ...]] = [tuple(config.parquet_split_primary_keys)]
    groups.extend((key,) for key in config.parquet_split_fallback_keys)
    return groups


def _split_value_to_json(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except TypeError:
        pass
    if hasattr(value, "item") and not isinstance(value, (str, bytes)):
        try:
            value = value.item()
        except Exception:
            pass
    return str(value)


def _group_split_key_values(keys: tuple[str, ...], group_value: object) -> dict[str, str | None]:
    if len(keys) == 1:
        if isinstance(group_value, tuple):
            values = (group_value[0] if group_value else None,)
        elif isinstance(group_value, list):
            values = (group_value[0] if group_value else None,)
        else:
            values = (group_value,)
    else:
        values = group_value if isinstance(group_value, tuple) else (group_value,)
    return {key: _split_value_to_json(value) for key, value in zip(keys, values, strict=False)}


def _probe_parquet_size(frame: pd.DataFrame, temp_dir: Path) -> int:
    temp_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".parquet", dir=temp_dir, delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        frame.to_parquet(temp_path, index=False)
        return temp_path.stat().st_size
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _split_frame_to_plans(
    frame: pd.DataFrame,
    *,
    key_groups: list[tuple[str, ...]],
    split_key_values: dict[str, str | None] | None = None,
    max_bytes: int,
    temp_dir: Path,
) -> list[_DatasetChunkPlan]:
    effective_split_values = split_key_values or {}
    if frame.empty:
        return [_DatasetChunkPlan(frame=frame.reset_index(drop=True), split_key_values=effective_split_values)]

    size_bytes = _probe_parquet_size(frame, temp_dir)
    if size_bytes <= max_bytes or (len(frame) == 1 and not key_groups):
        return [_DatasetChunkPlan(frame=frame.reset_index(drop=True), split_key_values=effective_split_values)]

    if key_groups:
        current_keys = tuple(key for key in key_groups[0] if key in frame.columns)
        if current_keys:
            grouped = list(frame.groupby(list(current_keys), sort=True, dropna=False, observed=False))
            if grouped:
                plans: list[_DatasetChunkPlan] = []
                for group_value, group_frame in grouped:
                    plans.extend(
                        _split_frame_to_plans(
                            group_frame.reset_index(drop=True),
                            key_groups=key_groups[1:],
                            split_key_values={**effective_split_values, **_group_split_key_values(current_keys, group_value)},
                            max_bytes=max_bytes,
                            temp_dir=temp_dir,
                        )
                    )
                return plans
        return _split_frame_to_plans(
            frame.reset_index(drop=True),
            key_groups=key_groups[1:],
            split_key_values=effective_split_values,
            max_bytes=max_bytes,
            temp_dir=temp_dir,
        )

    if len(frame) == 1:
        return [_DatasetChunkPlan(frame=frame.reset_index(drop=True), split_key_values=effective_split_values)]

    midpoint = max(1, len(frame) // 2)
    left = frame.iloc[:midpoint].reset_index(drop=True)
    right = frame.iloc[midpoint:].reset_index(drop=True)
    return _split_frame_to_plans(
        left,
        key_groups=[],
        split_key_values=effective_split_values,
        max_bytes=max_bytes,
        temp_dir=temp_dir,
    ) + _split_frame_to_plans(
        right,
        key_groups=[],
        split_key_values=effective_split_values,
        max_bytes=max_bytes,
        temp_dir=temp_dir,
    )


def _write_chunk_frame(frame: pd.DataFrame, path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, index=False)
    return path.stat().st_size


def _build_manifest(
    *,
    output_path: Path,
    config: RiskDatasetConfig,
    generated_at: datetime,
    source_report_paths: list[Path],
    total_candidates: int,
    joined: pd.DataFrame,
    labeled_rows: int,
    feature_rows: int,
    duplicates: int,
) -> tuple[RiskDatasetManifest, list[RiskDatasetChunkRecord]]:
    chunk_groups = _config_split_key_groups(config)
    with tempfile.TemporaryDirectory(dir=output_path.parent, prefix=f".{output_path.stem}.risk-dataset-probe.") as probe_dir_name:
        chunk_plans = _split_frame_to_plans(
            joined,
            key_groups=chunk_groups,
            max_bytes=config.max_parquet_file_size_bytes,
            temp_dir=Path(probe_dir_name),
        )

    if len(chunk_plans) == 1:
        chunk_paths = [output_path.resolve()]
    else:
        chunk_paths = [output_path.with_name(f"{output_path.stem}.part-{index:03d}{output_path.suffix}").resolve() for index in range(len(chunk_plans))]

    files: list[RiskDatasetChunkRecord] = []
    total_bytes = 0
    for index, (plan, chunk_path) in enumerate(zip(chunk_plans, chunk_paths, strict=False)):
        size_bytes = _write_chunk_frame(plan.frame, chunk_path)
        total_bytes += size_bytes
        files.append(
            RiskDatasetChunkRecord(
                path=str(chunk_path),
                row_count=len(plan.frame),
                size_bytes=size_bytes,
                chunk_index=index,
                split_key_values=plan.split_key_values,
            )
        )

    manifest = RiskDatasetManifest(
        generated_at=generated_at,
        dataset_version=config.dataset_version,
        label_version=config.label_version,
        feature_version=config.feature_version,
        config_hash=_config_hash(config),
        source_report_paths=[str(path.resolve()) for path in source_report_paths],
        total_candidates=total_candidates,
        labeled_rows=labeled_rows,
        feature_rows=feature_rows,
        joined_rows=len(joined),
        dropped_label_rows=max(0, total_candidates - labeled_rows),
        dropped_feature_rows=max(0, total_candidates - feature_rows),
        duplicate_candidate_ids=duplicates,
        output_path=str(chunk_paths[0]),
        max_parquet_file_size_bytes=config.max_parquet_file_size_bytes,
        primary_split_keys=list(config.parquet_split_primary_keys),
        fallback_split_keys=list(config.parquet_split_fallback_keys),
        chunk_count=len(files),
        total_parquet_bytes=total_bytes,
        files=files,
    )
    return manifest, files


def _write_partitioned_dataset(
    *,
    joined: pd.DataFrame,
    output_path: Path,
    config: RiskDatasetConfig,
    source_report_paths: list[Path],
    total_candidates: int,
    labeled_rows: int,
    feature_rows: int,
    duplicates: int,
) -> RiskDatasetManifest:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    manifest, _ = _build_manifest(
        output_path=output_path,
        config=config,
        generated_at=datetime.now(UTC),
        source_report_paths=source_report_paths,
        total_candidates=total_candidates,
        joined=joined,
        labeled_rows=labeled_rows,
        feature_rows=feature_rows,
        duplicates=duplicates,
    )
    manifest_path = output_path.with_suffix(".manifest.json")
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def _run_symbol_map(report_paths: list[Path]) -> dict[str, str]:
    symbols: dict[str, str] = {}
    for report_path in report_paths:
        report = BacktestReport.model_validate_json(report_path.read_text(encoding="utf-8"))
        for result in report.results:
            if result.symbol:
                symbols[result.run_id] = result.symbol
    return symbols


def _candidate_run_map(label_df: pd.DataFrame, feature_df: pd.DataFrame) -> dict[str, str]:
    if "run_id" not in label_df.columns and "run_id" not in feature_df.columns:
        return {}
    frames: list[pd.DataFrame] = []
    if "run_id" in label_df.columns:
        frames.append(label_df[["candidate_id", "run_id"]])
    if "run_id" in feature_df.columns:
        frames.append(feature_df[["candidate_id", "run_id"]])
    if not frames:
        return {}
    mapping = pd.concat(frames, ignore_index=True)
    mapping = mapping.dropna(subset=["candidate_id", "run_id"]).drop_duplicates("candidate_id", keep="last")
    return dict(zip(mapping["candidate_id"], mapping["run_id"]))


def _ensure_symbol_column(
    frame: pd.DataFrame,
    *,
    run_symbol_map: dict[str, str],
    candidate_run_map: dict[str, str],
) -> pd.DataFrame:
    symbol = (
        frame["symbol"].astype("object")
        if "symbol" in frame.columns
        else pd.Series(pd.NA, index=frame.index, dtype="object")
    )
    if "run_id" not in frame.columns and candidate_run_map:
        frame["run_id"] = frame["candidate_id"].map(candidate_run_map)
    if run_symbol_map and "run_id" in frame.columns:
        symbol = symbol.where(pd.notna(symbol), frame["run_id"].map(run_symbol_map))
    frame["symbol"] = symbol.astype("category")
    return frame


def build_labels_from_frame(
    candidates: list[EnrichedCandidate],
    *,
    frame: pd.DataFrame,
    config: RiskDatasetConfig,
    feature_atr_by_candidate: dict[str, float | None] | None = None,
) -> list[OutcomeLabelRecord]:
    labels: list[OutcomeLabelRecord] = []
    atr_map = feature_atr_by_candidate or {}
    for candidate in candidates:
        decision_idx = bar_index_at_or_before(frame, candidate.timestamp)
        if decision_idx is None:
            labels.append(
                OutcomeLabelRecord(
                    candidate_id=candidate.candidate_id,
                    label_version=config.label_version,
                    entry_price=candidate.entry_price,
                    horizon_bars=candidate.planned_horizon_bars,
                    stop_pct=candidate.planned_stop_pct,
                    target_pct=candidate.planned_target_pct,
                    mae_pct=0.0,
                    mae_abs_pct=0.0,
                    mae_atr=None,
                    mfe_pct=0.0,
                    final_return_pct=0.0,
                    realized_R=0.0,
                    hit_stop=False,
                    hit_target=False,
                    hit_stop_before_target=False,
                    bars_held=0,
                    exit_reason="DATA_ERROR",
                    label_quality_flag="MISSING_BARS",
                )
            )
            continue

        if candidate.side != "LONG":
            raise NotImplementedError("SHORT candidate labeling is not implemented in V1")

        labels.append(
            label_long_candidate(
                candidate_id=candidate.candidate_id,
                label_version=config.label_version,
                entry_price=candidate.entry_price,
                entry_type=candidate.entry_type,
                fill_model=candidate.fill_model,
                planned_stop_pct=candidate.planned_stop_pct,
                planned_target_pct=candidate.planned_target_pct,
                planned_horizon_bars=candidate.planned_horizon_bars,
                decision_idx=decision_idx,
                frame=frame,
                atr_14_pct=atr_map.get(candidate.candidate_id),
                ambiguous_intrabar_policy=config.ambiguous_intrabar_policy,
            )
        )
    return labels


def build_features_from_frame(
    candidates: list[EnrichedCandidate],
    *,
    frame: pd.DataFrame,
    config: RiskDatasetConfig,
    benchmark_frame: pd.DataFrame | None = None,
) -> list[FeatureSnapshotRecord]:
    snapshots: list[FeatureSnapshotRecord] = []
    for candidate in candidates:
        snapshots.append(
            build_feature_snapshot(
                candidate,
                frame=frame,
                config=config,
                benchmark_frame=benchmark_frame,
            )
        )
    return snapshots


def build_labels(
    candidates: list[EnrichedCandidate],
    *,
    bar_store: BarStore,
    config: RiskDatasetConfig,
    feature_atr_by_candidate: dict[str, float | None] | None = None,
) -> list[OutcomeLabelRecord]:
    labels: list[OutcomeLabelRecord] = []
    atr_map = feature_atr_by_candidate or {}
    for candidate in candidates:
        frame = bar_store.get_symbol_frame(candidate)
        labels.extend(
            build_labels_from_frame(
                [candidate],
                frame=frame,
                config=config,
                feature_atr_by_candidate={candidate.candidate_id: atr_map.get(candidate.candidate_id)},
            )
        )
    return labels


def build_features(
    candidates: list[EnrichedCandidate],
    *,
    bar_store: BarStore,
    config: RiskDatasetConfig,
    benchmark_frames: dict[tuple[str, str, str | None], pd.DataFrame],
) -> list[FeatureSnapshotRecord]:
    snapshots: list[FeatureSnapshotRecord] = []
    for candidate in candidates:
        frame = bar_store.get_symbol_frame(candidate)
        benchmark = bar_store.get_benchmark_frame(
            candidate,
            default_symbol=config.default_benchmark_symbol,
            benchmark_frames=benchmark_frames,
        )
        snapshots.extend(
            build_features_from_frame(
                [candidate],
                frame=frame,
                config=config,
                benchmark_frame=benchmark,
            )
        )
    return snapshots


def _load_sidecar_frames(report_path: Path) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    paths = default_artifact_paths(resolve_results_root(report_path), report_path.stem)
    labels_path = Path(paths.labels_parquet_path) if paths.labels_parquet_path else None
    features_path = Path(paths.features_parquet_path) if paths.features_parquet_path else None
    if labels_path and features_path and labels_path.exists() and features_path.exists():
        return pd.read_parquet(labels_path), pd.read_parquet(features_path)
    if paths.manifest_path and Path(paths.manifest_path).exists():
        from app.backtests.artifacts import _concat_shard_parquet_rows

        labels_rows = _concat_shard_parquet_rows(Path(paths.manifest_path), "labels")
        features_rows = _concat_shard_parquet_rows(Path(paths.manifest_path), "features")
        if labels_rows and features_rows:
            return pd.DataFrame(labels_rows), pd.DataFrame(features_rows)
    return None


def _load_joined_dataset_from_sidecars(
    report_paths: list[Path],
) -> pd.DataFrame | None:
    frames: list[pd.DataFrame] = []
    for report_path in report_paths:
        run_symbol_map = _run_symbol_map([report_path])
        sidecars = _load_sidecar_frames(report_path)
        if sidecars is None:
            return None
        label_df, feature_df = sidecars
        try:
            candidates, _ = load_candidates_from_reports([report_path])
        except Exception as exc:
            from app.risk.data.report_loader import CandidateLoadError

            if isinstance(exc, CandidateLoadError) and "No candidates found" in str(exc):
                candidates = []
            else:
                raise

        # If the report JSON omitted candidate logs, fall back to a reduced join using only
        # label + feature sidecars. This supports risk-model training but drops candidate metadata.
        if candidates:
            candidate_df = pd.DataFrame([_candidate_row(c) for c in candidates])
        else:
            candidate_df = pd.DataFrame(
                {
                    "candidate_id": pd.concat([label_df["candidate_id"], feature_df["candidate_id"]])
                    .dropna()
                    .unique()
                }
            )
            if "feature_timestamp" in feature_df.columns and "timestamp" not in candidate_df.columns:
                # Provide a reasonable time column for downstream sorting/splitting.
                # This is best-effort and may not exactly equal the candidate timestamp.
                ts = feature_df[["candidate_id", "feature_timestamp"]].dropna().drop_duplicates("candidate_id", keep="last")
                candidate_df = candidate_df.merge(ts, on="candidate_id", how="left")
                candidate_df = candidate_df.rename(columns={"feature_timestamp": "timestamp"})
        candidate_run_map = _candidate_run_map(label_df, feature_df)

        label_join_cols = [
            col
            for col in label_df.columns
            if (col not in candidate_df.columns or col == "candidate_id") and col not in {"label_version", "run_id"}
        ]
        feature_join_cols = [
            col
            for col in feature_df.columns
            if (col not in candidate_df.columns or col == "candidate_id")
            and col not in {"feature_version", "run_id", "metadata_features_json"}
        ]
        joined = candidate_df.merge(label_df[label_join_cols], on="candidate_id", how="inner")
        joined = joined.merge(feature_df[feature_join_cols], on="candidate_id", how="inner")

        # When candidate logs are missing from the report JSON and no candidate sidecar exists,
        # synthesize the training-critical candidate fields from labels/features sidecars.
        #
        # - `planned_stop_pct` / `planned_horizon_bars` are required by downstream risk modeling
        #   and correspond 1:1 with the label inputs.
        # - `side` is currently always LONG in V1 labeling/features.
        if "planned_stop_pct" not in joined.columns and "stop_pct" in joined.columns:
            joined["planned_stop_pct"] = joined["stop_pct"]
        if "planned_horizon_bars" not in joined.columns and "horizon_bars" in joined.columns:
            joined["planned_horizon_bars"] = joined["horizon_bars"]
        if "side" not in joined.columns:
            joined["side"] = "LONG"
        joined = _ensure_symbol_column(joined, run_symbol_map=run_symbol_map, candidate_run_map=candidate_run_map)

        frames.append(joined)

    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def build_risk_dataset(
    report_paths: list[Path],
    *,
    output_path: Path,
    config_path: Path | None = None,
    config: RiskDatasetConfig | None = None,
    cache_dir: str | None = None,
) -> RiskDatasetManifest:
    effective_config = config or load_risk_dataset_config(config_path)
    if cache_dir:
        effective_config = effective_config.model_copy(update={"cache_directory": cache_dir})

    joined_from_sidecars = _load_joined_dataset_from_sidecars(report_paths)
    if joined_from_sidecars is not None:
        try:
            candidates, duplicates = load_candidates_from_reports(
                report_paths,
                default_benchmark=effective_config.default_benchmark_symbol,
            )
            total_candidates = len(candidates)
        except Exception as exc:
            from app.risk.data.report_loader import CandidateLoadError

            if isinstance(exc, CandidateLoadError) and "No candidates found" in str(exc):
                duplicates = 0
                total_candidates = int(joined_from_sidecars["candidate_id"].nunique()) if "candidate_id" in joined_from_sidecars.columns else len(joined_from_sidecars)
            else:
                raise
        joined = joined_from_sidecars.copy()
        joined.insert(0, "dataset_version", effective_config.dataset_version)
        joined.insert(1, "label_version", effective_config.label_version)
        joined.insert(2, "feature_version", effective_config.feature_version)
        return _write_partitioned_dataset(
            joined=joined,
            output_path=output_path,
            config=effective_config,
            source_report_paths=report_paths,
            total_candidates=total_candidates,
            labeled_rows=len(joined),
            feature_rows=len(joined),
            duplicates=duplicates,
        )

    candidates, duplicates = load_candidates_from_reports(
        report_paths,
        default_benchmark=effective_config.default_benchmark_symbol,
    )

    cache_config = DataCacheConfig(
        enabled=effective_config.cache_enabled,
        directory=effective_config.cache_directory,
    )
    bar_store = BarStore(cache_config=cache_config)
    bar_store.prepare(candidates, lookback_bars=effective_config.lookback_bars)
    benchmark_frames = bar_store.prepare_benchmarks(
        candidates,
        lookback_bars=effective_config.lookback_bars,
        default_symbol=effective_config.default_benchmark_symbol,
    )

    features = build_features(
        candidates,
        bar_store=bar_store,
        config=effective_config,
        benchmark_frames=benchmark_frames,
    )
    atr_by_candidate = {snap.candidate_id: snap.atr_14_pct for snap in features}
    labels = build_labels(
        candidates,
        bar_store=bar_store,
        config=effective_config,
        feature_atr_by_candidate=atr_by_candidate,
    )

    candidate_df = pd.DataFrame([_candidate_row(c) for c in candidates])
    label_df = pd.DataFrame([_label_row(l) for l in labels])
    feature_df = pd.DataFrame([_feature_row(f) for f in features])

    label_join_cols = [
        col
        for col in label_df.columns
        if (col not in candidate_df.columns or col == "candidate_id") and col != "label_version"
    ]
    feature_join_cols = [
        col
        for col in feature_df.columns
        if (col not in candidate_df.columns or col == "candidate_id") and col != "feature_version"
    ]

    joined = candidate_df.merge(label_df[label_join_cols], on="candidate_id", how="inner")
    joined = joined.merge(feature_df[feature_join_cols], on="candidate_id", how="inner")
    joined.insert(0, "dataset_version", effective_config.dataset_version)
    joined.insert(1, "label_version", effective_config.label_version)
    joined.insert(2, "feature_version", effective_config.feature_version)
    return _write_partitioned_dataset(
        joined=joined,
        output_path=output_path,
        config=effective_config,
        source_report_paths=report_paths,
        total_candidates=len(candidates),
        labeled_rows=len(labels),
        feature_rows=len(features),
        duplicates=duplicates,
    )
