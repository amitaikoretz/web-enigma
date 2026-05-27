from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from app.backtests.artifacts import (
    default_artifact_paths,
    hydrate_report_from_artifacts,
    resolve_results_root,
)
from app.config.models import DataCacheConfig
from app.output.models import FeatureSnapshotRecord, OutcomeLabelRecord
from app.risk.data.bars import BarStore, bar_index_at_or_before
from app.risk.data.report_loader import load_candidates_from_reports
from app.risk.features.assemble import build_feature_snapshot
from app.risk.labels.path_labels import label_long_candidate
from app.risk.models import EnrichedCandidate, RiskDatasetConfig, RiskDatasetManifest


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
        sidecars = _load_sidecar_frames(report_path)
        if sidecars is None:
            return None
        label_df, feature_df = sidecars
        paths = default_artifact_paths(resolve_results_root(report_path), report_path.stem)
        candidates, _ = load_candidates_from_reports([report_path])
        if not candidates:
            continue
        candidate_df = pd.DataFrame([_candidate_row(c) for c in candidates])
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
        candidates, duplicates = load_candidates_from_reports(
            report_paths,
            default_benchmark=effective_config.default_benchmark_symbol,
        )
        joined = joined_from_sidecars.copy()
        joined.insert(0, "dataset_version", effective_config.dataset_version)
        joined.insert(1, "label_version", effective_config.label_version)
        joined.insert(2, "feature_version", effective_config.feature_version)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        joined.to_parquet(output_path, index=False)
        manifest_path = output_path.with_suffix(".manifest.json")
        manifest = RiskDatasetManifest(
            generated_at=datetime.now(UTC),
            dataset_version=effective_config.dataset_version,
            label_version=effective_config.label_version,
            feature_version=effective_config.feature_version,
            config_hash=_config_hash(effective_config),
            source_report_paths=[str(path.resolve()) for path in report_paths],
            total_candidates=len(candidates),
            labeled_rows=len(joined),
            feature_rows=len(joined),
            joined_rows=len(joined),
            dropped_label_rows=0,
            dropped_feature_rows=0,
            duplicate_candidate_ids=duplicates,
            output_path=str(output_path.resolve()),
        )
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return manifest

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

    output_path.parent.mkdir(parents=True, exist_ok=True)
    joined.to_parquet(output_path, index=False)

    manifest_path = output_path.with_suffix(".manifest.json")
    manifest = RiskDatasetManifest(
        generated_at=datetime.now(UTC),
        dataset_version=effective_config.dataset_version,
        label_version=effective_config.label_version,
        feature_version=effective_config.feature_version,
        config_hash=_config_hash(effective_config),
        source_report_paths=[str(path.resolve()) for path in report_paths],
        total_candidates=len(candidates),
        labeled_rows=len(labels),
        feature_rows=len(features),
        joined_rows=len(joined),
        dropped_label_rows=len(candidates) - len(labels),
        dropped_feature_rows=len(candidates) - len(features),
        duplicate_candidate_ids=duplicates,
        output_path=str(output_path.resolve()),
    )
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest
