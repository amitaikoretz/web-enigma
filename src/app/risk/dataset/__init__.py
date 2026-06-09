from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.risk.dataset.reader import RiskDatasetReader

if TYPE_CHECKING:
    from app.risk.dataset.builder import (
        build_features_from_frame,
        build_labels_from_frame,
        build_risk_dataset,
        load_risk_dataset_config,
    )

__all__ = [
    "RiskDatasetReader",
    "build_features_from_frame",
    "build_labels_from_frame",
    "build_risk_dataset",
    "load_risk_dataset_config",
]


def __getattr__(name: str) -> Any:
    if name in {
        "build_features_from_frame",
        "build_labels_from_frame",
        "build_risk_dataset",
        "load_risk_dataset_config",
    }:
        from app.risk.dataset.builder import (
            build_features_from_frame,
            build_labels_from_frame,
            build_risk_dataset,
            load_risk_dataset_config,
        )

        return {
            "build_features_from_frame": build_features_from_frame,
            "build_labels_from_frame": build_labels_from_frame,
            "build_risk_dataset": build_risk_dataset,
            "load_risk_dataset_config": load_risk_dataset_config,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
