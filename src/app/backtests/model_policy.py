from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Mapping

import numpy as np
import pandas as pd
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from app.config.models import BacktestModelPolicyConfig, ModelArtifactRef
from app.db.session import get_session_factory
from app.output.models import FeatureSnapshotRecord
from app.risk.features.assemble import build_feature_snapshot
from app.risk.models import EnrichedCandidate, RiskDatasetConfig
from app.risk.persistence import SqlAlchemyRiskModelRepository
from app.strategies.candidates import EntryIntent
from app.strategies.core import Bar, PositionState, StrategyContext, StrategyDecision

ModelFamily = Literal["forecast", "risk"]

_DEFAULT_MIN_STOP_BPS = 5.0
_DEFAULT_STOP_VOL_MULTIPLIER = 1.5
_DEFAULT_TARGET_VOL_BPS = 20.0
_DEFAULT_FLOOR_VOL_BPS = 5.0
_DEFAULT_MAX_PARTICIPATION_RATE = 0.02
_DEFAULT_MAX_NOTIONAL_FRACTION = 0.02


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:  # noqa: BLE001
        pass
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _feature_payload(snapshot: FeatureSnapshotRecord) -> dict[str, float | int | str | None]:
    payload = snapshot.model_dump(mode="python")
    metadata_features = payload.pop("metadata_features", {})
    if isinstance(metadata_features, dict):
        for key, value in metadata_features.items():
            payload[key] = value
    return payload


def _bars_to_frame(bars: list[Bar]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
    return pd.DataFrame(
        [
            {
                "Open": float(bar.open),
                "High": float(bar.high),
                "Low": float(bar.low),
                "Close": float(bar.close),
                "Volume": float(bar.volume),
            }
            for bar in bars
        ],
        index=pd.DatetimeIndex([bar.timestamp for bar in bars], tz="UTC"),
    )


def _candidate_for_context(
    context: StrategyContext,
    *,
    strategy_id: str,
    entry_intent: EntryIntent,
    fill_model: str,
    data_source: str,
    run_id: str = "backtest",
) -> EnrichedCandidate:
    symbol = context.symbol or "UNKNOWN"
    return EnrichedCandidate(
        candidate_id=hashlib.sha256(
            f"{strategy_id}|{symbol}|{context.bar.iso_timestamp}|LONG".encode("utf-8")
        ).hexdigest()[:16],
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp=context.bar.iso_timestamp,
        side="LONG",
        entry_price=float(entry_intent.entry_price),
        entry_type="CLOSE" if fill_model == "close" else "NEXT_OPEN",
        planned_stop_pct=float(entry_intent.planned_stop_pct),
        planned_target_pct=(
            float(entry_intent.planned_target_pct) if entry_intent.planned_target_pct is not None else None
        ),
        planned_horizon_bars=int(entry_intent.planned_horizon_bars),
        signal_score=entry_intent.signal_score,
        signal_reason=entry_intent.signal_reason,
        metadata=dict(entry_intent.metadata),
        was_traded=False,
        reject_reason=None,
        run_id=run_id,
        resolution=None,
        feed=None,
        data_source=data_source,
        fill_model=fill_model,
        start_date=None,
        end_date=None,
        benchmark_symbol=None,
        source_report_path="",
        csv_path=None,
    )


def _feature_snapshot_from_context(
    context: StrategyContext,
    *,
    strategy_id: str,
    entry_intent: EntryIntent,
    fill_model: str,
    data_source: str,
    risk_dataset_config: RiskDatasetConfig | None = None,
) -> FeatureSnapshotRecord | None:
    config = risk_dataset_config or RiskDatasetConfig()
    candidate = _candidate_for_context(
        context,
        strategy_id=strategy_id,
        entry_intent=entry_intent,
        fill_model=fill_model,
        data_source=data_source,
    )
    frame = _bars_to_frame(list(context.bars))
    benchmark_frame = _bars_to_frame(list(context.benchmark_bars)) if context.benchmark_bars is not None else None
    snapshot = build_feature_snapshot(candidate, frame=frame, config=config, benchmark_frame=benchmark_frame)
    if snapshot.feature_quality_flag != "OK":
        return None
    return snapshot


def _resolve_ref_from_repo(
    ref: ModelArtifactRef,
    *,
    family: ModelFamily,
    session_factory: sessionmaker[Session] | None = None,
) -> tuple[Path, list[str], str | None]:
    resolved_session_factory = session_factory or get_session_factory()
    repo_family = "return_forecast" if family == "forecast" else "risk"
    repo = SqlAlchemyRiskModelRepository(resolved_session_factory, family=repo_family)
    if ref.group_id is None:
        raise ValueError("group_id is required for repository-backed model references")
    detail = repo.get_detail(ref.group_id)
    if detail is None:
        raise ValueError(f"{family} model group '{ref.group_id}' not found")
    preferred_keys = [ref.target_key] if ref.target_key else []
    if family == "forecast":
        preferred_keys.extend(["forecast_return", "return", "mae"])
    else:
        preferred_keys.extend(["mae", "stop_prob"])
    target_row = None
    for key in preferred_keys:
        if not key:
            continue
        for row in detail.targets:
            if row.target_key == key and row.model_artifact_path:
                target_row = row
                break
        if target_row is not None:
            break
    if target_row is None:
        for row in detail.targets:
            if row.model_artifact_path:
                target_row = row
                break
    if target_row is None or not target_row.model_artifact_path:
        raise ValueError(f"{family} model group '{ref.group_id}' does not have a trained artifact yet")

    feature_columns = target_row.feature_columns or []
    return Path(target_row.model_artifact_path), list(feature_columns), target_row.target_key


def resolve_model_artifact_ref(
    ref: ModelArtifactRef,
    *,
    family: ModelFamily,
    session_factory: sessionmaker[Session] | None = None,
) -> tuple[Path, list[str], str | None]:
    if ref.group_id is not None:
        return _resolve_ref_from_repo(ref, family=family, session_factory=session_factory)

    if ref.model_artifact_path is None:
        raise ValueError("model_artifact_path is required when group_id is not provided")

    resolved_path = Path(ref.model_artifact_path)
    return resolved_path, [], ref.target_key


@dataclass(frozen=True)
class LoadedModelArtifact:
    artifact_path: Path
    family: ModelFamily
    target_key: str | None
    feature_columns: list[str]
    artifact_type: str
    coefficients: list[float] = field(default_factory=list)
    intercept: float = 0.0
    scaler_mean: list[float] | None = None
    scaler_scale: list[float] | None = None
    classes: list[Any] | None = None
    positive_rate: float | None = None
    calibration_x_thresholds: list[float] | None = None
    calibration_y_thresholds: list[float] | None = None

    @classmethod
    def from_path(cls, path: str | Path, *, family: ModelFamily, target_key: str | None = None) -> "LoadedModelArtifact":
        artifact_path = Path(path)
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"Model artifact must be a JSON object: {artifact_path}")

        feature_columns = list(
            payload.get("feature_cols")
            or payload.get("selected_features")
            or payload.get("feature_columns")
            or []
        )
        coefficients = list(
            payload.get("coef")
            or payload.get("coefficients")
            or payload.get("scaler_coef")
            or []
        )
        intercept = _as_float(payload.get("intercept")) or 0.0
        scaler_mean = payload.get("scaler_mean")
        scaler_scale = payload.get("scaler_scale")
        classes = payload.get("classes")
        positive_rate = _as_float(payload.get("positive_rate"))
        calibration_x = payload.get("iso_x_thresholds")
        calibration_y = payload.get("iso_y_thresholds")
        if not feature_columns:
            raise ValueError(f"Model artifact does not declare feature columns: {artifact_path}")
        return cls(
            artifact_path=artifact_path,
            family=family,
            target_key=target_key,
            feature_columns=feature_columns,
            artifact_type=str(payload.get("type") or payload.get("model_type") or "linear"),
            coefficients=[float(value) for value in coefficients],
            intercept=float(intercept),
            scaler_mean=[float(value) for value in scaler_mean] if isinstance(scaler_mean, list) else None,
            scaler_scale=[float(value) for value in scaler_scale] if isinstance(scaler_scale, list) else None,
            classes=list(classes) if isinstance(classes, list) else None,
            positive_rate=positive_rate,
            calibration_x_thresholds=[float(value) for value in calibration_x] if isinstance(calibration_x, list) else None,
            calibration_y_thresholds=[float(value) for value in calibration_y] if isinstance(calibration_y, list) else None,
        )

    @property
    def kind(self) -> str:
        if self.classes is not None or "logreg" in self.artifact_type or "classification" in self.artifact_type:
            return "classification"
        return "regression"

    def score(self, features: Mapping[str, Any]) -> float:
        values = np.asarray([_as_float(features.get(name)) or 0.0 for name in self.feature_columns], dtype=float)
        if self.scaler_mean is not None and self.scaler_scale is not None:
            mean = np.asarray(self.scaler_mean, dtype=float)
            scale = np.asarray(self.scaler_scale, dtype=float)
            scale = np.where(scale == 0.0, 1.0, scale)
            values = (values - mean) / scale

        if not self.coefficients:
            if self.positive_rate is not None:
                return float(self.positive_rate)
            raise ValueError(f"Model artifact has no coefficients: {self.artifact_path}")

        raw_score = float(np.dot(np.asarray(self.coefficients, dtype=float), values) + self.intercept)
        if self.kind != "classification":
            return raw_score

        if self.positive_rate is not None and "DummyClassifier" in self.artifact_type:
            return float(self.positive_rate)

        probability = float(1.0 / (1.0 + np.exp(-raw_score)))
        if self.calibration_x_thresholds and self.calibration_y_thresholds:
            xs = np.asarray(self.calibration_x_thresholds, dtype=float)
            ys = np.asarray(self.calibration_y_thresholds, dtype=float)
            if xs.size == ys.size and xs.size >= 2:
                probability = float(np.interp(probability, xs, ys, left=ys[0], right=ys[-1]))
        return probability


class ModelEvaluation(BaseModel):
    family: ModelFamily
    model_path: str | None
    target_key: str | None
    score: float | None
    score_bps: float | None
    feature_count: int


@dataclass(frozen=True)
class BacktestModelPolicy:
    config: BacktestModelPolicyConfig
    strategy_id: str
    data_source: str
    fill_model: str
    forecast_model: LoadedModelArtifact | None = None
    risk_model: LoadedModelArtifact | None = None
    risk_dataset_config: RiskDatasetConfig | None = None

    def _evaluate_model(
        self,
        *,
        model: LoadedModelArtifact | None,
        family: ModelFamily,
        features: Mapping[str, Any],
    ) -> ModelEvaluation:
        if model is None:
            return ModelEvaluation(
                family=family,
                model_path=None,
                target_key=None,
                score=None,
                score_bps=None,
                feature_count=0,
            )
        score = model.score(features)
        return ModelEvaluation(
            family=family,
            model_path=str(model.artifact_path),
            target_key=model.target_key,
            score=score,
            score_bps=float(score * 10000.0),
            feature_count=len(model.feature_columns),
        )

    def _base_edge_bps(self, decision: StrategyDecision) -> float:
        if decision.entry_intent is None:
            return 0.0
        signal_score = decision.entry_intent.signal_score
        if signal_score is None:
            signal_score = 1.0
        return float(max(0.0, signal_score) * self.config.target_edge_bps)

    def _fallback_risk_bps(self, snapshot: FeatureSnapshotRecord) -> float:
        atr_14_pct = _as_float(snapshot.atr_14_pct)
        realized_vol_20 = _as_float(snapshot.realized_vol_20)
        if atr_14_pct is not None and atr_14_pct > 0:
            return float(atr_14_pct * 10000.0)
        if realized_vol_20 is not None and realized_vol_20 > 0:
            return float(realized_vol_20 * 10000.0)
        return _DEFAULT_FLOOR_VOL_BPS

    def apply(
        self,
        context: StrategyContext,
        decision: StrategyDecision,
    ) -> StrategyDecision:
        if decision.action != "buy" or decision.entry_intent is None:
            return decision
        if self.forecast_model is None and self.risk_model is None:
            return decision

        snapshot = _feature_snapshot_from_context(
            context,
            strategy_id=self.strategy_id,
            entry_intent=decision.entry_intent,
            fill_model=self.fill_model,
            data_source=self.data_source,
            risk_dataset_config=self.risk_dataset_config,
        )
        if snapshot is None:
            return StrategyDecision.hold(
                "model_policy_warmup",
                auditor_rejection=True,
                entry_intent=decision.entry_intent,
            )

        feature_payload = _feature_payload(snapshot)
        forecast_eval = self._evaluate_model(model=self.forecast_model, family="forecast", features=feature_payload)
        risk_eval = self._evaluate_model(model=self.risk_model, family="risk", features=feature_payload)
        entry_price = float(decision.entry_intent.entry_price)

        signal_score = decision.entry_intent.signal_score if decision.entry_intent.signal_score is not None else 1.0
        if float(signal_score) < self.config.min_signal_score:
            updated_intent = EntryIntent(
                entry_price=entry_price,
                planned_stop_pct=float(decision.entry_intent.planned_stop_pct),
                planned_target_pct=decision.entry_intent.planned_target_pct,
                planned_horizon_bars=int(decision.entry_intent.planned_horizon_bars),
                signal_score=decision.entry_intent.signal_score,
                signal_reason=decision.entry_intent.signal_reason,
                metadata={
                    **decision.entry_intent.metadata,
                    "model_policy": {
                        "mode": "forecast_only"
                        if self.forecast_model is not None and self.risk_model is None
                        else "risk_only"
                        if self.risk_model is not None and self.forecast_model is None
                        else "combined",
                        "forecast": forecast_eval.model_dump(mode="json"),
                        "risk": risk_eval.model_dump(mode="json"),
                        "signal_score": signal_score,
                        "min_signal_score": self.config.min_signal_score,
                    },
                },
            )
            return StrategyDecision.hold(
                "model_policy_below_signal_floor",
                auditor_rejection=True,
                entry_intent=updated_intent,
            )

        expected_edge_bps = forecast_eval.score_bps if forecast_eval.score_bps is not None else self._base_edge_bps(decision)
        if expected_edge_bps <= self.config.threshold_bps:
            updated_intent = EntryIntent(
                entry_price=entry_price,
                planned_stop_pct=float(decision.entry_intent.planned_stop_pct),
                planned_target_pct=decision.entry_intent.planned_target_pct,
                planned_horizon_bars=int(decision.entry_intent.planned_horizon_bars),
                signal_score=decision.entry_intent.signal_score,
                signal_reason=decision.entry_intent.signal_reason,
                metadata={
                    **decision.entry_intent.metadata,
                    "model_policy": {
                        "mode": "forecast_only"
                        if self.forecast_model is not None and self.risk_model is None
                        else "risk_only"
                        if self.risk_model is not None and self.forecast_model is None
                        else "combined",
                        "forecast": forecast_eval.model_dump(mode="json"),
                        "risk": risk_eval.model_dump(mode="json"),
                        "expected_edge_bps": expected_edge_bps,
                        "threshold_bps": self.config.threshold_bps,
                    },
                },
            )
            return StrategyDecision.hold(
                "model_policy_below_threshold",
                auditor_rejection=True,
                entry_intent=updated_intent,
            )

        forecast_risk_bps = risk_eval.score_bps if risk_eval.score_bps is not None else self._fallback_risk_bps(snapshot)
        forecast_risk_bps = max(_DEFAULT_FLOOR_VOL_BPS, float(abs(forecast_risk_bps)))
        stop_distance_bps = max(_DEFAULT_MIN_STOP_BPS, forecast_risk_bps * _DEFAULT_STOP_VOL_MULTIPLIER)
        stop_distance_pct = stop_distance_bps / 10000.0
        account_equity = float(context.equity or 100000.0)
        desired_risk_dollars = account_equity * self.config.max_risk_fraction
        risk_based_shares = desired_risk_dollars / max(entry_price * stop_distance_pct, 1e-9)
        quality_scale = float(
            np.clip((abs(expected_edge_bps) - self.config.threshold_bps) / max(self.config.target_edge_bps, 1e-9), 0.0, 1.0)
        )
        vol_scale = float(np.clip(_DEFAULT_TARGET_VOL_BPS / max(forecast_risk_bps, _DEFAULT_FLOOR_VOL_BPS), 0.0, 5.0))
        liquidity_cap_shares = max(
            0.0,
            min(
                _DEFAULT_MAX_PARTICIPATION_RATE * float(context.bar.volume),
                (_DEFAULT_MAX_NOTIONAL_FRACTION * account_equity) / max(entry_price, 1e-9),
            ),
        )
        final_shares = max(0.0, min(risk_based_shares * quality_scale * vol_scale, liquidity_cap_shares))
        final_shares_units = int(round(final_shares))
        if final_shares_units <= 0:
            updated_intent = EntryIntent(
                entry_price=entry_price,
                planned_stop_pct=float(decision.entry_intent.planned_stop_pct),
                planned_target_pct=decision.entry_intent.planned_target_pct,
                planned_horizon_bars=int(decision.entry_intent.planned_horizon_bars),
                signal_score=decision.entry_intent.signal_score,
                signal_reason=decision.entry_intent.signal_reason,
                metadata={
                    **decision.entry_intent.metadata,
                    "model_policy": {
                        "mode": "forecast_only"
                        if self.forecast_model is not None and self.risk_model is None
                        else "risk_only"
                        if self.risk_model is not None and self.forecast_model is None
                        else "combined",
                        "forecast": forecast_eval.model_dump(mode="json"),
                        "risk": risk_eval.model_dump(mode="json"),
                        "expected_edge_bps": expected_edge_bps,
                        "forecast_risk_bps": forecast_risk_bps,
                        "threshold_bps": self.config.threshold_bps,
                    },
                },
            )
            return StrategyDecision.hold(
                "model_policy_zero_size",
                auditor_rejection=True,
                entry_intent=updated_intent,
            )

        updated_intent = EntryIntent(
            entry_price=entry_price,
            planned_stop_pct=float(stop_distance_pct),
            planned_target_pct=decision.entry_intent.planned_target_pct,
            planned_horizon_bars=int(decision.entry_intent.planned_horizon_bars),
            signal_score=decision.entry_intent.signal_score,
            signal_reason=decision.entry_intent.signal_reason,
            metadata={
                **decision.entry_intent.metadata,
                "model_policy": {
                    "mode": "forecast_only"
                    if self.forecast_model is not None and self.risk_model is None
                    else "risk_only"
                    if self.risk_model is not None and self.forecast_model is None
                    else "combined",
                    "forecast": forecast_eval.model_dump(mode="json"),
                    "risk": risk_eval.model_dump(mode="json"),
                    "expected_edge_bps": expected_edge_bps,
                    "forecast_risk_bps": forecast_risk_bps,
                    "threshold_bps": self.config.threshold_bps,
                    "target_edge_bps": self.config.target_edge_bps,
                    "quality_scale": quality_scale,
                    "vol_scale": vol_scale,
                    "risk_based_shares": risk_based_shares,
                    "liquidity_cap_shares": liquidity_cap_shares,
                },
            },
        )
        return StrategyDecision.buy(
            float(final_shares_units),
            "model_policy_combined"
            if self.forecast_model is not None and self.risk_model is not None
            else "model_policy_single",
            entry_intent=updated_intent,
        )


def _resolve_ref(
    ref: ModelArtifactRef | None,
    *,
    family: ModelFamily,
    session_factory: sessionmaker[Session] | None = None,
) -> LoadedModelArtifact | None:
    if ref is None:
        return None
    if ref.model_artifact_path is not None:
        return LoadedModelArtifact.from_path(ref.model_artifact_path, family=family, target_key=ref.target_key)
    path, feature_columns, target_key = _resolve_ref_from_repo(ref, family=family, session_factory=session_factory)
    model = LoadedModelArtifact.from_path(path, family=family, target_key=target_key)
    if feature_columns:
        model = LoadedModelArtifact(
            artifact_path=model.artifact_path,
            family=model.family,
            target_key=model.target_key,
            feature_columns=feature_columns,
            artifact_type=model.artifact_type,
            coefficients=model.coefficients,
            intercept=model.intercept,
            scaler_mean=model.scaler_mean,
            scaler_scale=model.scaler_scale,
            classes=model.classes,
            positive_rate=model.positive_rate,
            calibration_x_thresholds=model.calibration_x_thresholds,
            calibration_y_thresholds=model.calibration_y_thresholds,
        )
    return model


def resolve_backtest_model_policy(
    config: BacktestModelPolicyConfig | None,
    *,
    strategy_id: str,
    data_source: str,
    fill_model: str,
    risk_dataset_config: RiskDatasetConfig | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> BacktestModelPolicy | None:
    if config is None:
        return None
    forecast_model = _resolve_ref(config.forecast_model, family="forecast", session_factory=session_factory)
    risk_model = _resolve_ref(config.risk_model, family="risk", session_factory=session_factory)
    if forecast_model is None and risk_model is None:
        return None
    return BacktestModelPolicy(
        config=config,
        strategy_id=strategy_id,
        data_source=data_source,
        fill_model=fill_model,
        forecast_model=forecast_model,
        risk_model=risk_model,
        risk_dataset_config=risk_dataset_config,
    )
