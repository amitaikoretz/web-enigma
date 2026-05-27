from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from app.config.models import BacktestRunConfig
from app.output.models import CandidateRecord, FeatureSnapshotRecord, OutcomeLabelRecord, RunResult
from app.risk.data.report_loader import enrich_candidate_from_run
from app.risk.dataset.builder import build_features_from_frame, build_labels_from_frame
from app.risk.models import RiskDatasetConfig, RunRiskAuxiliaryRows

logger = logging.getLogger(__name__)


def build_risk_auxiliary_for_run(
    *,
    result: RunResult,
    run: BacktestRunConfig,
    symbol_frame: pd.DataFrame,
    benchmark_frame: pd.DataFrame | None = None,
    config: RiskDatasetConfig | None = None,
    source_report_path: str = "",
    default_benchmark: str = "SPY",
) -> RunRiskAuxiliaryRows:
    effective_config = config or RiskDatasetConfig()
    if not result.candidates:
        return RunRiskAuxiliaryRows()

    run_cfg = run.model_dump(mode="json")
    enriched = []
    for candidate in result.candidates:
        try:
            enriched.append(
                enrich_candidate_from_run(
                    candidate,
                    result=result,
                    run_cfg=run_cfg,
                    source_report_path=source_report_path,
                    default_benchmark=default_benchmark,
                )
            )
        except ValueError as exc:
            logger.warning("Skipping candidate %s during risk auxiliary build: %s", candidate.candidate_id, exc)
            continue

    if not enriched:
        return RunRiskAuxiliaryRows()

    try:
        features = build_features_from_frame(
            enriched,
            frame=symbol_frame,
            config=effective_config,
            benchmark_frame=benchmark_frame,
        )
        atr_by_candidate = {snap.candidate_id: snap.atr_14_pct for snap in features}
        labels = build_labels_from_frame(
            enriched,
            frame=symbol_frame,
            config=effective_config,
            feature_atr_by_candidate=atr_by_candidate,
        )
        return RunRiskAuxiliaryRows(labels=labels, features=features)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Risk auxiliary build failed for run %s: %s", result.run_id, exc)
        return RunRiskAuxiliaryRows()


def enrich_run_candidates(
    candidates: list[CandidateRecord],
    *,
    result: RunResult,
    run_cfg: dict[str, Any],
    source_report_path: str,
    default_benchmark: str = "SPY",
):
    return [
        enrich_candidate_from_run(
            candidate,
            result=result,
            run_cfg=run_cfg,
            source_report_path=source_report_path,
            default_benchmark=default_benchmark,
        )
        for candidate in candidates
    ]
