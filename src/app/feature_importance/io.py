from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.feature_importance.models import (
    FeatureImportanceArtifact,
    FeatureImportanceRow,
    FeatureImportanceTarget,
)


def build_linear_feature_importance(
    *,
    target_key: str,
    feature_names: list[str],
    coefficients: list[float],
    source: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> FeatureImportanceArtifact:
    if len(feature_names) != len(coefficients):
        raise ValueError("feature_names and coefficients must have the same length")

    abs_values = np.abs(np.asarray(coefficients, dtype=float))
    total = float(abs_values.sum())
    rows = []
    for feature, coef, abs_value in zip(feature_names, coefficients, abs_values, strict=False):
        importance = float(abs_value / total) if total > 0 else 0.0
        rows.append(
            FeatureImportanceRow(
                feature=feature,
                importance=importance,
                signed_importance=float(coef),
            )
        )

    rows.sort(key=lambda row: row.importance, reverse=True)
    return FeatureImportanceArtifact(
        generated_at=datetime.now(UTC),
        source=source,
        targets=[FeatureImportanceTarget(target_key=target_key, rows=rows)],
        metadata=metadata or {},
    )


def write_feature_importance_artifact(path: str | Path, artifact: FeatureImportanceArtifact) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(artifact.model_dump(mode="json"), indent=2), encoding="utf-8")
    return output_path


def load_feature_importance_artifact(path: str | Path | None) -> FeatureImportanceArtifact | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.is_file():
        return None
    return FeatureImportanceArtifact.model_validate_json(candidate.read_text(encoding="utf-8"))
