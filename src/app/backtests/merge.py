from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from app import __version__
from app.backtests.artifacts import default_artifact_paths, hydrate_report_from_artifacts, resolve_results_root
from app.engine.aggregates import compute_report_aggregates
from app.backtests.sharding import ShardPlan, load_shard_manifest
from app.output.models import BacktestReport, RunResult


def _aggregate_status(successful: int, failed: int) -> str:
    if failed == 0:
        return "success"
    if successful == 0:
        return "failure"
    return "partial_failure"


def merge_shard_reports(
    plan: ShardPlan,
    *,
    original_config_raw: dict | None = None,
    input_config_path: str | None = None,
) -> BacktestReport:
    results: list[RunResult] = []
    for shard in plan.shards:
        shard_path = Path(shard.output_path)
        if not shard_path.exists():
            raise FileNotFoundError(f"Shard report not found: {shard_path}")
        shard_report = BacktestReport.model_validate_json(shard_path.read_text(encoding="utf-8"))
        shard_artifact_root = resolve_results_root(shard_path, shard_path.stem)
        shard_paths = default_artifact_paths(shard_artifact_root, shard_path.stem)
        shard_report = hydrate_report_from_artifacts(shard_report, paths=shard_paths)
        results.extend(shard_report.results)

    successful = sum(1 for result in results if result.status == "success")
    failed = len(results) - successful
    status = _aggregate_status(successful, failed)

    config_raw = original_config_raw
    if config_raw is None:
        config_path = Path(plan.config_path)
        if config_path.exists():
            import yaml

            loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                config_raw = loaded
        if config_raw is None and results:
            config_raw = {}

    config_sha256 = hashlib.sha256(json.dumps(config_raw, sort_keys=True).encode("utf-8")).hexdigest()

    return BacktestReport(
        generated_at=datetime.now(UTC),
        app_version=__version__,
        config_sha256=config_sha256,
        input_config_path=input_config_path or plan.config_path,
        input_config=config_raw or {},
        total_runs=len(results),
        successful_runs=successful,
        failed_runs=failed,
        status=status,  # type: ignore[arg-type]
        results=results,
        aggregates=compute_report_aggregates(results),
    )


def merge_from_manifest(
    manifest_path: Path,
    *,
    original_config_raw: dict | None = None,
    input_config_path: str | None = None,
) -> BacktestReport:
    plan = load_shard_manifest(manifest_path)
    return merge_shard_reports(
        plan,
        original_config_raw=original_config_raw,
        input_config_path=input_config_path,
    )


def merge_exit_code(report: BacktestReport) -> int:
    if report.status == "success":
        return 0
    if report.status == "partial_failure":
        return 10
    return 20
