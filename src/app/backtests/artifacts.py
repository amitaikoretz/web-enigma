from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, TypeVar

import pandas as pd

from app.backtests.models import BacktestArtifactEntry, BacktestArtifactSummaryItem
from app.backtests.persistence import BacktestArtifactPaths
from app.backtests.sharding import load_shard_manifest
from app.output.files import write_backtest_report_json
from app.output.models import (
    BacktestReport,
    CandidateRecord,
    EquityPoint,
    FeatureSnapshotRecord,
    OrderRecord,
    OutcomeLabelRecord,
    RejectionRecord,
    RunResult,
    TradeRecord,
)

RecordT = TypeVar("RecordT")

ArtifactFormat = Literal["json", "yaml", "parquet", "other"]
ArtifactRole = Literal["primary", "sidecar", "manifest", "shard"]
_INTERNAL_ARTIFACT_ROLES: frozenset[ArtifactRole] = frozenset({"manifest", "shard"})


@dataclass(frozen=True)
class _ArtifactSpec:
    kind: str
    label: str
    description: str
    format: ArtifactFormat
    role: ArtifactRole
    path_attr: str


_KNOWN_ARTIFACTS: tuple[_ArtifactSpec, ...] = (
    _ArtifactSpec(
        "config",
        "Submitted config",
        "Input YAML written when this backtest was submitted",
        "yaml",
        "primary",
        "config_path",
    ),
    _ArtifactSpec(
        "report_json",
        "Report summary",
        "Slim JSON index; detailed run data lives in sidecar files",
        "json",
        "primary",
        "report_json_path",
    ),
    _ArtifactSpec(
        "report_parquet",
        "Run summaries",
        "Per-run headline metrics: return, Sharpe, max drawdown, and trade counts",
        "parquet",
        "sidecar",
        "report_parquet_path",
    ),
    _ArtifactSpec(
        "candidates_json",
        "Entry candidates (JSON)",
        "Strategy entry signals evaluated each bar; hydrates the Candidates tab",
        "json",
        "sidecar",
        "candidates_json_path",
    ),
    _ArtifactSpec(
        "candidates_parquet",
        "Entry candidates",
        "Strategy entry signals evaluated each bar; hydrates the Candidates tab",
        "parquet",
        "sidecar",
        "candidates_parquet_path",
    ),
    _ArtifactSpec(
        "equity_parquet",
        "Equity curves",
        "Portfolio value time series per run; used in run and strategy charts",
        "parquet",
        "sidecar",
        "equity_parquet_path",
    ),
    _ArtifactSpec(
        "orders_parquet",
        "Orders",
        "Broker orders submitted during each run",
        "parquet",
        "sidecar",
        "orders_parquet_path",
    ),
    _ArtifactSpec(
        "trades_parquet",
        "Trades",
        "Closed trade records with PnL, size, and exit reason",
        "parquet",
        "sidecar",
        "trades_parquet_path",
    ),
    _ArtifactSpec(
        "rejections_parquet",
        "Signal rejections",
        "Filter and auditor reasons a signal was blocked",
        "parquet",
        "sidecar",
        "rejections_parquet_path",
    ),
    _ArtifactSpec(
        "labels_parquet",
        "Outcome labels",
        "Risk-model outcome labels for candidate events",
        "parquet",
        "sidecar",
        "labels_parquet_path",
    ),
    _ArtifactSpec(
        "features_parquet",
        "Feature snapshots",
        "Risk-model feature vectors at candidate events",
        "parquet",
        "sidecar",
        "features_parquet_path",
    ),
)

_DESCRIPTION_BY_KIND = {spec.kind: spec.description for spec in _KNOWN_ARTIFACTS}
_LABEL_BY_KIND = {spec.kind: spec.label for spec in _KNOWN_ARTIFACTS}

_SIDECAR_FILENAME_SUFFIXES: tuple[tuple[str, str], ...] = (
    (".candidates.json", "candidates_json"),
    (".candidates.parquet", "candidates_parquet"),
    (".equity.parquet", "equity_parquet"),
    (".orders.parquet", "orders_parquet"),
    (".trades.parquet", "trades_parquet"),
    (".rejections.parquet", "rejections_parquet"),
    (".labels.parquet", "labels_parquet"),
    (".features.parquet", "features_parquet"),
)


def _is_internal_artifact_path(path: Path) -> bool:
    return path.name == "manifest.json" or "shards" in path.parts


def _artifact_format_for_path(path: Path) -> ArtifactFormat:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".parquet":
        return "parquet"
    return "other"


def _match_sidecar_filename(name: str) -> str | None:
    for suffix, lookup_kind in _SIDECAR_FILENAME_SUFFIXES:
        if name.endswith(suffix):
            return lookup_kind
    return None


def _artifact_label_for_path(path: Path) -> str:
    name = path.name
    lookup_kind = _match_sidecar_filename(name)
    if lookup_kind is not None:
        return _LABEL_BY_KIND[lookup_kind]
    if name == "config.yaml":
        return _LABEL_BY_KIND["config"]
    if path.suffix == ".json" and "shards" in path.parts:
        return "Shard report"
    if path.suffix == ".json":
        return _LABEL_BY_KIND["report_json"]
    if path.suffix in {".yaml", ".yml"}:
        return _LABEL_BY_KIND["config"]
    if path.suffix == ".parquet" and "." not in path.stem:
        return _LABEL_BY_KIND["report_parquet"]
    return name


def _artifact_description_for_path(path: Path) -> str:
    name = path.name
    lookup_kind = _match_sidecar_filename(name)
    if lookup_kind is not None:
        return _DESCRIPTION_BY_KIND[lookup_kind]
    if name == "config.yaml":
        return _DESCRIPTION_BY_KIND["config"]
    if path.suffix == ".json" and "shards" not in path.parts:
        return _DESCRIPTION_BY_KIND["report_json"]
    if path.suffix in {".yaml", ".yml"}:
        return _DESCRIPTION_BY_KIND["config"]
    if path.suffix == ".parquet" and "." not in path.stem:
        return _DESCRIPTION_BY_KIND["report_parquet"]
    return "Auxiliary backtest output file"


def _artifact_role_for_path(path: Path) -> ArtifactRole:
    if path.name == "manifest.json":
        return "manifest"
    if "shards" in path.parts:
        return "shard"
    if path.suffix.lower() in {".yaml", ".yml"} or path.name.endswith(".json") and not path.name.endswith(".parquet"):
        if any(token in path.name for token in (".orders.", ".trades.", ".candidates.", ".equity.", ".rejections.", ".labels.", ".features.")):
            return "sidecar"
        return "primary"
    return "sidecar"


def _merge_artifact_paths(
    backtest_id: str,
    output_dir: Path,
    paths: BacktestArtifactPaths | None,
) -> BacktestArtifactPaths:
    merged = default_artifact_paths(output_dir, backtest_id)
    if paths is None:
        return merged

    report_json_path = paths.report_json_path or merged.report_json_path
    if report_json_path:
        report_path = Path(report_json_path)
        if report_path.is_file():
            merged = default_artifact_paths(resolve_results_root(report_path, backtest_id), backtest_id)

    return BacktestArtifactPaths(
        config_path=paths.config_path or merged.config_path,
        report_json_path=paths.report_json_path or merged.report_json_path,
        report_parquet_path=paths.report_parquet_path or merged.report_parquet_path,
        candidates_json_path=paths.candidates_json_path or merged.candidates_json_path,
        candidates_parquet_path=paths.candidates_parquet_path or merged.candidates_parquet_path,
        equity_parquet_path=paths.equity_parquet_path or merged.equity_parquet_path,
        orders_parquet_path=paths.orders_parquet_path or merged.orders_parquet_path,
        trades_parquet_path=paths.trades_parquet_path or merged.trades_parquet_path,
        rejections_parquet_path=paths.rejections_parquet_path or merged.rejections_parquet_path,
        labels_parquet_path=paths.labels_parquet_path or merged.labels_parquet_path,
        features_parquet_path=paths.features_parquet_path or merged.features_parquet_path,
        manifest_path=paths.manifest_path or merged.manifest_path,
    )


def _legacy_flat_paths(output_dir: Path, backtest_id: str) -> BacktestArtifactPaths:
    base = output_dir.resolve()
    return BacktestArtifactPaths(
        config_path=str(base / f"{backtest_id}.yaml"),
        report_json_path=str(base / f"{backtest_id}.json"),
        report_parquet_path=str(base / f"{backtest_id}.parquet"),
        candidates_json_path=str(base / f"{backtest_id}.candidates.json"),
        candidates_parquet_path=str(base / f"{backtest_id}.candidates.parquet"),
        equity_parquet_path=str(base / f"{backtest_id}.equity.parquet"),
        orders_parquet_path=str(base / f"{backtest_id}.orders.parquet"),
        trades_parquet_path=str(base / f"{backtest_id}.trades.parquet"),
        rejections_parquet_path=str(base / f"{backtest_id}.rejections.parquet"),
        labels_parquet_path=str(base / f"{backtest_id}.labels.parquet"),
        features_parquet_path=str(base / f"{backtest_id}.features.parquet"),
        manifest_path=str(base / backtest_id / "manifest.json"),
    )


def _entry_from_path(
    *,
    kind: str,
    label: str,
    description: str,
    format: ArtifactFormat,
    role: ArtifactRole,
    path: Path,
) -> BacktestArtifactEntry:
    stat = path.stat()
    return BacktestArtifactEntry(
        kind=kind,
        label=label,
        description=description,
        format=format,
        role=role,
        path=str(path.resolve()),
        size_bytes=stat.st_size,
    )


def inventory_backtest_artifacts(
    backtest_id: str,
    output_dir: Path,
    *,
    paths: BacktestArtifactPaths | None = None,
) -> list[BacktestArtifactEntry]:
    resolved_paths = _merge_artifact_paths(backtest_id, output_dir, paths)
    legacy_paths = _legacy_flat_paths(output_dir, backtest_id)
    work_dir = backtest_artifact_dir(output_dir, backtest_id)

    seen_paths: set[str] = set()
    entries: list[BacktestArtifactEntry] = []

    def add_entry(
        *,
        kind: str,
        label: str,
        description: str,
        format: ArtifactFormat,
        role: ArtifactRole,
        path_value: str | None,
    ) -> None:
        if not path_value:
            return
        path = Path(path_value)
        if _is_internal_artifact_path(path):
            return
        resolved = str(path.resolve())
        if resolved in seen_paths or not path.is_file():
            return
        seen_paths.add(resolved)
        entries.append(
            _entry_from_path(
                kind=kind,
                label=label,
                description=description,
                format=format,
                role=role,
                path=path,
            )
        )

    for spec in _KNOWN_ARTIFACTS:
        for paths_obj in (resolved_paths, legacy_paths):
            path_value = getattr(paths_obj, spec.path_attr)
            add_entry(
                kind=spec.kind,
                label=spec.label,
                description=spec.description,
                format=spec.format,
                role=spec.role,
                path_value=path_value,
            )

    if work_dir.is_dir():
        for path in sorted(work_dir.rglob("*")):
            if not path.is_file() or _is_internal_artifact_path(path):
                continue
            resolved = str(path.resolve())
            if resolved in seen_paths:
                continue
            seen_paths.add(resolved)
            entries.append(
                _entry_from_path(
                    kind=f"file:{path.name}",
                    label=_artifact_label_for_path(path),
                    description=_artifact_description_for_path(path),
                    format=_artifact_format_for_path(path),
                    role=_artifact_role_for_path(path),
                    path=path,
                )
            )

    role_order = {"primary": 0, "sidecar": 1}
    visible_entries = [entry for entry in entries if entry.role not in _INTERNAL_ARTIFACT_ROLES]
    visible_entries.sort(key=lambda entry: (role_order.get(entry.role, 99), entry.label, entry.path))
    return visible_entries


def summarize_backtest_artifacts(
    backtest_id: str,
    output_dir: Path,
    *,
    paths: BacktestArtifactPaths | None = None,
) -> list[BacktestArtifactSummaryItem]:
    return [
        BacktestArtifactSummaryItem(
            kind=entry.kind,
            label=entry.label,
            description=entry.description,
            format=entry.format,
            role=entry.role,
        )
        for entry in inventory_backtest_artifacts(backtest_id, output_dir, paths=paths)
    ]


def backtest_artifact_dir(output_dir: Path, backtest_id: str) -> Path:
    return output_dir.resolve() / backtest_id


def resolve_results_root(output_path: Path, backtest_id: str | None = None) -> Path:
    """Return the top-level results directory for a report output path."""
    bid = backtest_id or output_path.stem
    parent = output_path.parent
    if parent.name == bid:
        return parent.parent
    return parent


def flatten_outcome_labels(
    labels: list[OutcomeLabelRecord],
    *,
    run_id: str,
) -> list[dict]:
    rows: list[dict] = []
    for label in labels:
        payload = label.model_dump(mode="json")
        payload["run_id"] = run_id
        rows.append(payload)
    return rows


def flatten_feature_snapshots(
    features: list[FeatureSnapshotRecord],
    *,
    run_id: str,
) -> list[dict]:
    rows: list[dict] = []
    for feature in features:
        payload = feature.model_dump(mode="json")
        metadata = payload.pop("metadata_features", {})
        payload["metadata_features_json"] = json.dumps(metadata) if metadata else None
        payload["run_id"] = run_id
        rows.append(payload)
    return rows


def flatten_risk_auxiliary_for_report(
    report: BacktestReport,
    auxiliary_by_run: dict[str, tuple[list[OutcomeLabelRecord], list[FeatureSnapshotRecord]]],
) -> tuple[list[dict], list[dict]]:
    label_rows: list[dict] = []
    feature_rows: list[dict] = []
    for result in report.results:
        if result.run_id not in auxiliary_by_run:
            continue
        labels, features = auxiliary_by_run[result.run_id]
        label_rows.extend(flatten_outcome_labels(labels, run_id=result.run_id))
        feature_rows.extend(flatten_feature_snapshots(features, run_id=result.run_id))
    return label_rows, feature_rows


def _flatten_outcome_labels_from_report(report: BacktestReport) -> list[dict]:
    return []


def _flatten_feature_snapshots_from_report(report: BacktestReport) -> list[dict]:
    return []


def _write_shard_colocated_sidecars(
    report_json_path: Path,
    *,
    label_rows: list[dict],
    feature_rows: list[dict],
) -> None:
    if "shards" not in report_json_path.parts:
        return
    if label_rows:
        _write_parquet(label_rows, _shard_sidecar_path(report_json_path, "labels"))
    if feature_rows:
        _write_parquet(feature_rows, _shard_sidecar_path(report_json_path, "features"))


def persist_backtest_report(
    report: BacktestReport,
    output_path: Path,
    *,
    manifest_path: str | Path | None = None,
    risk_auxiliary_by_run: dict[str, tuple[list[OutcomeLabelRecord], list[FeatureSnapshotRecord]]] | None = None,
) -> BacktestArtifactPaths:
    write_backtest_report_json(report, output_path)
    backtest_id = output_path.stem
    paths = default_artifact_paths(resolve_results_root(output_path, backtest_id), backtest_id)
    resolved_manifest_path = (
        str(Path(manifest_path).resolve())
        if manifest_path is not None
        else paths.manifest_path
    )
    label_rows: list[dict] = []
    feature_rows: list[dict] = []
    if risk_auxiliary_by_run:
        label_rows, feature_rows = flatten_risk_auxiliary_for_report(report, risk_auxiliary_by_run)
        _write_shard_colocated_sidecars(
            output_path.resolve(),
            label_rows=label_rows,
            feature_rows=feature_rows,
        )
    return write_report_artifacts(
        report,
        paths=BacktestArtifactPaths(
            config_path=paths.config_path,
            report_json_path=str(output_path.resolve()),
            report_parquet_path=paths.report_parquet_path,
            candidates_parquet_path=paths.candidates_parquet_path,
            equity_parquet_path=paths.equity_parquet_path,
            orders_parquet_path=paths.orders_parquet_path,
            trades_parquet_path=paths.trades_parquet_path,
            rejections_parquet_path=paths.rejections_parquet_path,
            labels_parquet_path=paths.labels_parquet_path,
            features_parquet_path=paths.features_parquet_path,
            manifest_path=resolved_manifest_path,
        ),
        label_rows=label_rows,
        feature_rows=feature_rows,
    )


def default_artifact_paths(output_dir: Path, backtest_id: str) -> BacktestArtifactPaths:
    base = backtest_artifact_dir(output_dir, backtest_id)
    return BacktestArtifactPaths(
        config_path=str(base / f"{backtest_id}.yaml"),
        report_json_path=str(base / f"{backtest_id}.json"),
        report_parquet_path=str(base / f"{backtest_id}.parquet"),
        candidates_json_path=str(base / f"{backtest_id}.candidates.json"),
        candidates_parquet_path=str(base / f"{backtest_id}.candidates.parquet"),
        equity_parquet_path=str(base / f"{backtest_id}.equity.parquet"),
        orders_parquet_path=str(base / f"{backtest_id}.orders.parquet"),
        trades_parquet_path=str(base / f"{backtest_id}.trades.parquet"),
        rejections_parquet_path=str(base / f"{backtest_id}.rejections.parquet"),
        labels_parquet_path=str(base / f"{backtest_id}.labels.parquet"),
        features_parquet_path=str(base / f"{backtest_id}.features.parquet"),
        manifest_path=str(base / "manifest.json"),
    )


def _shard_sidecar_path(shard_output_path: Path, kind: str) -> Path:
    return shard_output_path.with_name(f"{shard_output_path.stem}.{kind}.parquet")


def _merge_grouped_records(
    left: dict[str, list[RecordT]],
    right: dict[str, list[RecordT]],
) -> dict[str, list[RecordT]]:
    merged = {run_id: list(records) for run_id, records in left.items()}
    for run_id, records in right.items():
        merged.setdefault(run_id, []).extend(records)
    return merged


def _resolve_shard_sidecar_path(manifest_path: Path, shard_id: str, shard_output_path: Path, kind: str) -> Path:
    candidates = (
        _shard_sidecar_path(shard_output_path, kind),
        manifest_path.parent / "shards" / f"{shard_id}.{kind}.parquet",
        manifest_path.parent / "shards" / shard_id / f"{shard_output_path.stem}.{kind}.parquet",
        manifest_path.parent / "shards" / f"{shard_output_path.stem}.{kind}.parquet",
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _load_grouped_from_shard_manifest(
    manifest_path: Path,
    *,
    loader: Callable[[Path], dict[str, list[RecordT]]],
    kind: str,
) -> dict[str, list[RecordT]]:
    plan = load_shard_manifest(manifest_path)
    grouped: dict[str, list[RecordT]] = {}
    for shard in plan.shards:
        sidecar_path = _resolve_shard_sidecar_path(
            manifest_path,
            shard.shard_id,
            Path(shard.output_path),
            kind,
        )
        if not sidecar_path.exists():
            continue
        grouped = _merge_grouped_records(grouped, loader(sidecar_path))
    return grouped


def _load_grouped_with_shard_fallback(
    paths: BacktestArtifactPaths,
    *,
    parquet_path: str | None,
    loader: Callable[[Path], dict[str, list[RecordT]]],
    kind: str,
) -> dict[str, list[RecordT]]:
    grouped: dict[str, list[RecordT]] = {}
    if parquet_path:
        path = Path(parquet_path)
        if path.exists():
            grouped = loader(path)
    if grouped or not paths.manifest_path:
        return grouped

    manifest_path = Path(paths.manifest_path)
    if not manifest_path.exists():
        return grouped
    return _load_grouped_from_shard_manifest(manifest_path, loader=loader, kind=kind)


def _concat_shard_parquet_rows(manifest_path: Path, kind: str) -> list[dict]:
    plan = load_shard_manifest(manifest_path)
    rows: list[dict] = []
    for shard in plan.shards:
        sidecar_path = _resolve_shard_sidecar_path(
            manifest_path,
            shard.shard_id,
            Path(shard.output_path),
            kind,
        )
        if not sidecar_path.exists():
            continue
        frame = pd.read_parquet(sidecar_path)
        if frame.empty:
            continue
        rows.extend(frame.to_dict(orient="records"))
    return rows


def _flatten_run_records(
    report: BacktestReport,
    *,
    attr: str,
) -> list[dict]:
    rows: list[dict] = []
    for result in report.results:
        for record in getattr(result, attr):
            payload = record.model_dump(mode="json")
            payload["run_id"] = result.run_id
            rows.append(payload)
    return rows


def _flatten_candidates(report: BacktestReport) -> list[dict]:
    rows: list[dict] = []
    for result in report.results:
        for candidate in result.candidates:
            payload = candidate.model_dump(mode="json")
            payload["run_id"] = result.run_id
            metadata = payload.pop("metadata", {})
            payload["metadata_json"] = json.dumps(metadata) if metadata else None
            rows.append(payload)
    return rows


def _flatten_equity(report: BacktestReport) -> list[dict]:
    rows: list[dict] = []
    for result in report.results:
        for point in result.equity_curve:
            rows.append(
                {
                    "run_id": result.run_id,
                    "datetime": point.datetime,
                    "value": point.value,
                }
            )
    return rows


def _report_summary_rows(report: BacktestReport) -> list[dict]:
    rows: list[dict] = []
    for result in report.results:
        summary = result.summary
        rows.append(
            {
                "run_id": result.run_id,
                "name": result.name,
                "status": result.status,
                "strategy": result.strategy,
                "symbol": result.symbol,
                "data_source": result.data_source,
                "start_value": summary.start_value if summary else None,
                "end_value": summary.end_value if summary else None,
                "return_pct": summary.return_pct if summary else None,
                "max_drawdown_pct": summary.max_drawdown_pct if summary else None,
                "sharpe_ratio": summary.sharpe_ratio if summary else None,
                "total_trades": summary.total_trades if summary else 0,
                "won_trades": summary.won_trades if summary else 0,
                "lost_trades": summary.lost_trades if summary else 0,
            }
        )
    return rows


def _write_parquet(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".parquet.tmp")
    pd.DataFrame(rows).to_parquet(temp_path, index=False)
    temp_path.replace(path)


def _maybe_write_parquet(rows: list[dict], path_value: str | None) -> str | None:
    if not rows or not path_value:
        return None
    _write_parquet(rows, Path(path_value))
    return path_value


def _load_grouped_from_parquet(
    path: Path,
    *,
    model_validate: Callable[[dict], RecordT],
) -> dict[str, list[RecordT]]:
    frame = pd.read_parquet(path)
    if frame.empty:
        return {}
    grouped: dict[str, list[RecordT]] = {}
    for _, row in frame.iterrows():
        run_id = str(row.get("run_id", ""))
        payload = row.to_dict()
        payload.pop("run_id", None)
        grouped.setdefault(run_id, []).append(model_validate(payload))
    return grouped


def _flatten_or_shard_sidecars(
    report: BacktestReport,
    *,
    paths: BacktestArtifactPaths,
    flatten: Callable[[], list[dict]],
    kind: str,
) -> list[dict]:
    rows = flatten()
    if rows or not paths.manifest_path:
        return rows

    manifest_path = Path(paths.manifest_path)
    if not manifest_path.exists():
        return rows
    return _concat_shard_parquet_rows(manifest_path, kind)


def write_report_artifacts(
    report: BacktestReport,
    *,
    paths: BacktestArtifactPaths,
    label_rows: list[dict] | None = None,
    feature_rows: list[dict] | None = None,
) -> BacktestArtifactPaths:
    if paths.report_parquet_path and report.results:
        _write_parquet(_report_summary_rows(report), Path(paths.report_parquet_path))

    candidates_parquet_path = _maybe_write_parquet(
        _flatten_or_shard_sidecars(
            report,
            paths=paths,
            flatten=lambda: _flatten_candidates(report),
            kind="candidates",
        ),
        paths.candidates_parquet_path,
    )
    equity_parquet_path = _maybe_write_parquet(
        _flatten_or_shard_sidecars(
            report,
            paths=paths,
            flatten=lambda: _flatten_equity(report),
            kind="equity",
        ),
        paths.equity_parquet_path,
    )
    orders_parquet_path = _maybe_write_parquet(
        _flatten_or_shard_sidecars(
            report,
            paths=paths,
            flatten=lambda: _flatten_run_records(report, attr="orders"),
            kind="orders",
        ),
        paths.orders_parquet_path,
    )
    trades_parquet_path = _maybe_write_parquet(
        _flatten_or_shard_sidecars(
            report,
            paths=paths,
            flatten=lambda: _flatten_run_records(report, attr="trades"),
            kind="trades",
        ),
        paths.trades_parquet_path,
    )
    rejections_parquet_path = _maybe_write_parquet(
        _flatten_or_shard_sidecars(
            report,
            paths=paths,
            flatten=lambda: _flatten_run_records(report, attr="rejections"),
            kind="rejections",
        ),
        paths.rejections_parquet_path,
    )
    labels_source = label_rows if label_rows is not None else []
    if not labels_source:
        labels_source = _flatten_or_shard_sidecars(
            report,
            paths=paths,
            flatten=lambda: _flatten_outcome_labels_from_report(report),
            kind="labels",
        )
    labels_parquet_path = _maybe_write_parquet(labels_source, paths.labels_parquet_path)
    features_source = feature_rows if feature_rows is not None else []
    if not features_source:
        features_source = _flatten_or_shard_sidecars(
            report,
            paths=paths,
            flatten=lambda: _flatten_feature_snapshots_from_report(report),
            kind="features",
        )
    features_parquet_path = _maybe_write_parquet(features_source, paths.features_parquet_path)

    return BacktestArtifactPaths(
        config_path=paths.config_path,
        report_json_path=paths.report_json_path,
        report_parquet_path=paths.report_parquet_path,
        candidates_json_path=None,
        candidates_parquet_path=candidates_parquet_path,
        equity_parquet_path=equity_parquet_path,
        orders_parquet_path=orders_parquet_path,
        trades_parquet_path=trades_parquet_path,
        rejections_parquet_path=rejections_parquet_path,
        labels_parquet_path=labels_parquet_path,
        features_parquet_path=features_parquet_path,
        manifest_path=paths.manifest_path,
    )


def load_candidates_from_parquet(path: Path) -> dict[str, list[CandidateRecord]]:
    frame = pd.read_parquet(path)
    if frame.empty:
        return {}
    grouped: dict[str, list[CandidateRecord]] = {}
    for _, row in frame.iterrows():
        run_id = str(row.get("run_id", ""))
        payload = row.to_dict()
        payload.pop("run_id", None)
        metadata_json = payload.pop("metadata_json", None)
        if metadata_json and not pd.isna(metadata_json):
            parsed = json.loads(str(metadata_json))
            payload["metadata"] = parsed if isinstance(parsed, dict) else {}
        else:
            payload["metadata"] = {}
        grouped.setdefault(run_id, []).append(CandidateRecord.model_validate(payload))
    return grouped


def load_equity_from_parquet(path: Path) -> dict[str, list[EquityPoint]]:
    frame = pd.read_parquet(path)
    if frame.empty:
        return {}
    grouped: dict[str, list[EquityPoint]] = {}
    for _, row in frame.iterrows():
        run_id = str(row.get("run_id", ""))
        grouped.setdefault(run_id, []).append(
            EquityPoint(
                datetime=str(row["datetime"]),
                value=float(row["value"]),
            )
        )
    return grouped


def load_orders_from_parquet(path: Path) -> dict[str, list[OrderRecord]]:
    return _load_grouped_from_parquet(path, model_validate=OrderRecord.model_validate)


def load_trades_from_parquet(path: Path) -> dict[str, list[TradeRecord]]:
    return _load_grouped_from_parquet(path, model_validate=TradeRecord.model_validate)


def load_rejections_from_parquet(path: Path) -> dict[str, list[RejectionRecord]]:
    return _load_grouped_from_parquet(path, model_validate=RejectionRecord.model_validate)


def load_labels_from_parquet(path: Path) -> dict[str, list[OutcomeLabelRecord]]:
    return _load_grouped_from_parquet(path, model_validate=OutcomeLabelRecord.model_validate)


def load_features_from_parquet(path: Path) -> dict[str, list[FeatureSnapshotRecord]]:
    frame = pd.read_parquet(path)
    if frame.empty:
        return {}
    grouped: dict[str, list[FeatureSnapshotRecord]] = {}
    for _, row in frame.iterrows():
        run_id = str(row.get("run_id", ""))
        payload = row.to_dict()
        payload.pop("run_id", None)
        metadata_json = payload.pop("metadata_features_json", None)
        if metadata_json and not pd.isna(metadata_json):
            parsed = json.loads(str(metadata_json))
            payload["metadata_features"] = parsed if isinstance(parsed, dict) else {}
        else:
            payload["metadata_features"] = {}
        grouped.setdefault(run_id, []).append(FeatureSnapshotRecord.model_validate(payload))
    return grouped


def _load_candidates_by_run(paths: BacktestArtifactPaths) -> dict[str, list[CandidateRecord]]:
    candidates_by_run = _load_grouped_with_shard_fallback(
        paths,
        parquet_path=paths.candidates_parquet_path,
        loader=load_candidates_from_parquet,
        kind="candidates",
    )
    if candidates_by_run:
        return candidates_by_run
    if paths.candidates_json_path:
        json_path = Path(paths.candidates_json_path)
        if json_path.exists():
            candidates_by_run = {}
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                for entry in raw:
                    if not isinstance(entry, dict):
                        continue
                    run_id = str(entry.pop("run_id", ""))
                    metadata_json = entry.pop("metadata_json", None)
                    if metadata_json and not entry.get("metadata"):
                        parsed = json.loads(metadata_json) if isinstance(metadata_json, str) else metadata_json
                        entry["metadata"] = parsed if isinstance(parsed, dict) else {}
                    candidates_by_run.setdefault(run_id, []).append(CandidateRecord.model_validate(entry))
            return candidates_by_run
    return {}


def hydrate_report_from_artifacts(
    report: BacktestReport,
    *,
    paths: BacktestArtifactPaths,
) -> BacktestReport:
    candidates_by_run = _load_candidates_by_run(paths)
    equity_by_run = _load_grouped_with_shard_fallback(
        paths,
        parquet_path=paths.equity_parquet_path,
        loader=load_equity_from_parquet,
        kind="equity",
    )
    orders_by_run = _load_grouped_with_shard_fallback(
        paths,
        parquet_path=paths.orders_parquet_path,
        loader=load_orders_from_parquet,
        kind="orders",
    )
    trades_by_run = _load_grouped_with_shard_fallback(
        paths,
        parquet_path=paths.trades_parquet_path,
        loader=load_trades_from_parquet,
        kind="trades",
    )
    rejections_by_run = _load_grouped_with_shard_fallback(
        paths,
        parquet_path=paths.rejections_parquet_path,
        loader=load_rejections_from_parquet,
        kind="rejections",
    )

    if not any(
        (
            candidates_by_run,
            equity_by_run,
            orders_by_run,
            trades_by_run,
            rejections_by_run,
        )
    ):
        return report

    hydrated_results: list[RunResult] = []
    for result in report.results:
        updates: dict = {}
        if not result.candidates and result.run_id in candidates_by_run:
            updates["candidates"] = candidates_by_run[result.run_id]
        if not result.equity_curve and result.run_id in equity_by_run:
            updates["equity_curve"] = equity_by_run[result.run_id]
        if not result.orders and result.run_id in orders_by_run:
            updates["orders"] = orders_by_run[result.run_id]
        if not result.trades and result.run_id in trades_by_run:
            updates["trades"] = trades_by_run[result.run_id]
        if not result.rejections and result.run_id in rejections_by_run:
            updates["rejections"] = rejections_by_run[result.run_id]
        if updates:
            hydrated_results.append(result.model_copy(update=updates))
        else:
            hydrated_results.append(result)

    return report.model_copy(update={"results": hydrated_results})
