from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from pathlib import Path

import pandas as pd
from sqlalchemy import select

from app.db.models import DailyIndexFeatureRun, RiskModelGroup, RiskModelTarget
from app.db.session import get_db_session
from app.daily_index_forecast.records import (
    DailyIndexFeatureRecord,
    DailyIndexLabelRecord,
    frame_to_records,
    records_to_frame,
)
from tests.conftest import build_backtest_client


class _FakeDailyIndexArgoSubmitter:
    def __init__(self) -> None:
        self.config = SimpleNamespace(namespace="daily-index-tests")
        self.submissions: list[dict] = []

    def _http_request(self, method: str, path: str, json: dict) -> SimpleNamespace:
        self.submissions.append({"method": method, "path": path, "json": json})
        return SimpleNamespace(status_code=200, text="")

    def get_workflow_phase(self, workflow_name: str, *, namespace: str | None = None) -> str:
        return "Running"

    def get_workflow(self, workflow_name: str, *, namespace: str | None = None) -> dict:
        return {
            "status": {
                "phase": "Failed",
                "progress": "25/100",
                "nodes": {
                    "train-node": {
                        "displayName": "train",
                        "templateName": "train",
                        "phase": "Failed",
                        "finishedAt": "2026-06-05T10:00:00Z",
                        "outputs": {
                            "parameters": [
                                {"name": "error-exception", "value": "ValueError: boom"},
                                {"name": "error-code-location", "value": "train.py:42"},
                                {"name": "error-call-stack", "value": "train.py:42\npipeline.py:88"},
                                {"name": "error-traceback", "value": "traceback text"},
                            ]
                        },
                    }
                },
            }
        }


def _seed_completed_daily_index_model(
    client,
    *,
    group_id: str,
    feature_run_id: str,
    manifest_path: Path,
) -> None:
    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    now = datetime.now(UTC)
    feature_run = session.get(DailyIndexFeatureRun, feature_run_id)
    assert feature_run is not None
    feature_run.symbol = "SPY"
    feature_run.benchmark_symbol = "QQQ"
    feature_run.decision_times_json = ["09:45"]
    feature_run.start_date = datetime(2024, 1, 1, tzinfo=UTC).date()
    feature_run.end_date = datetime(2024, 1, 31, tzinfo=UTC).date()
    feature_run.status = "succeeded"
    feature_run.argo_namespace = "daily-index-tests"
    feature_run.argo_workflow_name = "daily-index-forecast-abc123"
    feature_run.params_json = {
        "name": "Seeded forecast",
        "universe": {
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
            "decision_times": ["09:45"],
            "symbols": [{"symbol": "SPY", "data": {"type": "yahoo", "symbol": "SPY", "interval": "5m"}}],
            "benchmark": {"symbol": "QQQ", "data": {"type": "yahoo", "symbol": "QQQ", "interval": "5m"}},
        },
        "feature_config": {
            "opening_window_minutes": 15,
            "rolling_sessions": [5, 20],
            "benchmark_sessions": [5, 20],
            "use_calendar_features": True,
            "use_cross_market_features": True,
        },
        "walk_forward": {
            "train_days": 90,
            "validation_days": 10,
            "test_days": 10,
            "step_days": 10,
            "embargo_days": 1,
            "holdout_days": 20,
        },
        "train_config": {"alpha_grid": [0.25, 1.0, 4.0], "residual_distribution": "normal", "random_seed": 7},
        "costs": {"spread_bps": 1.5, "slippage_bps": 1.0, "impact_bps": 0.5},
        "data_cache": {},
    }
    feature_run.artifact_dir = "/tmp/daily-index-forecast/feature-run"
    feature_run.manifest_path = str(manifest_path)
    feature_run.features_parquet_path = str(manifest_path.parent / "features.parquet")
    feature_run.labels_parquet_path = str(manifest_path.parent / "labels.parquet")
    feature_run.summary_metrics_json = {
        "holdout": {
            "regression": {"mae": 1.234, "rmse": 2.345},
            "classification": {"accuracy": 0.6},
            "calibration": {"brier_score": 0.15},
            "quantile": {"coverage_90": 0.9},
        },
        "aggregate": {
            "validation": {"regression": {"mae": 1.5}},
            "test": {"regression": {"mae": 1.4}},
        },
    }
    feature_run.created_at = now
    feature_run.updated_at = now

    group = session.get(RiskModelGroup, group_id)
    assert group is not None
    group.family = "daily_index_forecast"
    group.name = "Seeded forecast"
    group.status = "succeeded"
    group.argo_namespace = "daily-index-tests"
    group.argo_workflow_name = "daily-index-forecast-abc123"
    group.feature_run_id = feature_run_id
    group.params_json = feature_run.params_json
    group.artifact_dir = "/tmp/daily-index-forecast/group"
    group.summary_metrics_json = feature_run.summary_metrics_json
    group.created_at = now
    group.updated_at = now

    target = session.scalar(
        select(RiskModelTarget).where(
            RiskModelTarget.group_id == group_id,
            RiskModelTarget.target_key == "regression",
        )
    )
    if target is None:
        session.add(
            RiskModelTarget(
                group_id=group_id,
                target_key="regression",
                task_type="regression",
                status="succeeded",
                model_artifact_path="/tmp/daily-index-forecast/model.json",
                metrics_json={"regression": {"mae": 1.234}},
                dataset_manifest_path=str(manifest_path),
                feature_columns_json=["open_price", "rolling_return_20"],
            )
        )
    else:
        target.task_type = "regression"
        target.status = "succeeded"
        target.model_artifact_path = "/tmp/daily-index-forecast/model.json"
        target.metrics_json = {"regression": {"mae": 1.234}}
        target.dataset_manifest_path = str(manifest_path)
        target.feature_columns_json = ["open_price", "rolling_return_20"]
        target.updated_at = now

    session.commit()
    session.close()


def test_daily_index_feature_and_label_records_round_trip_parquet(tmp_path: Path) -> None:
    feature_records = [
        DailyIndexFeatureRecord(
            symbol="SPY",
            session_date=datetime(2024, 1, 2, tzinfo=UTC).date(),
            decision_time="09:45",
            decision_timestamp=datetime(2024, 1, 2, 14, 45, tzinfo=UTC),
            session_open_timestamp=datetime(2024, 1, 2, 14, 30, tzinfo=UTC),
            session_close_timestamp=datetime(2024, 1, 2, 21, 0, tzinfo=UTC),
            bars_seen=4,
            opening_window_minutes=15,
            open_price=100.0,
            high_price=101.0,
            low_price=99.5,
            last_price=100.5,
            volume_so_far=125000.0,
            dollar_volume_so_far=12550000.0,
            opening_window_return_pct=0.005,
            opening_window_range_pct=0.015,
            opening_window_close_location_pct=0.666,
            gap_return_pct=0.002,
            prior_session_return_pct=0.01,
            prior_session_range_pct=0.02,
            prior_session_volume=200000.0,
            prior_session_realized_volatility=0.03,
            rolling_return_5=0.02,
            rolling_return_20=0.08,
            rolling_volatility_5=0.01,
            rolling_volatility_20=0.02,
            rolling_volume_z_20=1.5,
            benchmark_return_5=0.01,
            benchmark_return_20=0.04,
            benchmark_volatility_20=0.015,
            relative_return_20=0.04,
            correlation_to_benchmark_20=0.8,
            beta_to_benchmark_20=1.1,
            day_of_week=1,
            month=1,
            is_month_start=False,
            is_month_end=False,
            minutes_since_open=15,
            minutes_to_close=375,
        )
    ]
    label_records = [
        DailyIndexLabelRecord(
            symbol="SPY",
            session_date=datetime(2024, 1, 2, tzinfo=UTC).date(),
            decision_time="09:45",
            decision_timestamp=datetime(2024, 1, 2, 14, 45, tzinfo=UTC),
            exit_timestamp=datetime(2024, 1, 2, 21, 0, tzinfo=UTC),
            entry_price=100.5,
            exit_price=101.5,
            return_to_close_pct=0.00995,
            return_to_close_bps=99.5,
            net_return_after_cost_bps=94.5,
            positive_after_cost=True,
        )
    ]

    feature_frame = records_to_frame(feature_records)
    label_frame = records_to_frame(label_records)
    features_path = tmp_path / "features.parquet"
    labels_path = tmp_path / "labels.parquet"
    feature_frame.to_parquet(features_path, index=False)
    label_frame.to_parquet(labels_path, index=False)

    loaded_features = frame_to_records(pd.read_parquet(features_path), DailyIndexFeatureRecord)
    loaded_labels = frame_to_records(pd.read_parquet(labels_path), DailyIndexLabelRecord)

    assert loaded_features == feature_records
    assert loaded_labels == label_records


def test_daily_index_forecast_api_create_detail_retry_delete(tmp_path: Path, monkeypatch) -> None:
    client = build_backtest_client(tmp_path)
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", str(tmp_path / "results"))
    monkeypatch.setattr(client.app.state.deps.daily_index_forecast_models, "_argo_submitter", _FakeDailyIndexArgoSubmitter())

    response = client.post(
        "/daily-index-forecast-models",
        json={
            "name": "Seeded forecast",
            "universe": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "decision_times": ["09:45"],
                "symbols": [
                    {
                        "symbol": "SPY",
                        "data": {"type": "yahoo", "symbol": "SPY", "interval": "5m"},
                    }
                ],
                "benchmark": {"symbol": "QQQ", "data": {"type": "yahoo", "symbol": "QQQ", "interval": "5m"}},
            },
            "feature_config": {
                "opening_window_minutes": 15,
                "rolling_sessions": [5, 20],
                "benchmark_sessions": [5, 20],
                "use_calendar_features": True,
                "use_cross_market_features": True,
            },
            "walk_forward": {
                "train_days": 90,
                "validation_days": 10,
                "test_days": 10,
                "step_days": 10,
                "embargo_days": 1,
                "holdout_days": 20,
                "min_train_rows": 100,
                "min_validation_rows": 25,
                "min_test_rows": 25,
                "min_holdout_rows": 25,
            },
            "train_config": {
                "alpha_grid": [0.25, 1.0, 4.0],
                "residual_distribution": "normal",
                "random_seed": 7,
            },
            "costs": {"spread_bps": 1.5, "slippage_bps": 1.0, "impact_bps": 0.5},
            "data_cache": {},
        },
    )
    assert response.status_code == 202
    created = response.json()
    group_id = created["group_id"]
    feature_run_id = created["feature_run_id"]

    manifest_path = tmp_path / "results" / "daily-index-forecast-models" / feature_run_id / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        """
        {
          "generated_at": "2026-06-05T00:00:00Z",
          "dataset_version": "daily_index_dataset_v1",
          "feature_version": "daily_index_features_v1",
          "label_version": "daily_index_labels_v1",
          "model_version": "daily_index_model_v1",
          "config_hash": "abc123",
          "symbol_count": 1,
          "benchmark_symbol": "QQQ",
          "start_date": "2024-01-01",
          "end_date": "2024-01-31",
          "decision_times": ["09:45"],
          "total_source_rows": 10,
          "feature_rows": 9,
          "label_rows": 9,
          "joined_rows": 9,
          "dropped_feature_rows": 1,
          "dropped_label_rows": 1,
          "output_path": "/tmp/dataset.parquet",
          "features_path": "/tmp/features.parquet",
          "labels_path": "/tmp/labels.parquet",
          "feature_columns": ["open_price", "rolling_return_20"]
        }
        """.strip(),
        encoding="utf-8",
    )

    _seed_completed_daily_index_model(client, group_id=group_id, feature_run_id=feature_run_id, manifest_path=manifest_path)

    list_response = client.get("/daily-index-forecast-models")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert len(list_payload) == 1
    assert list_payload[0]["group_id"] == group_id
    assert list_payload[0]["symbol"] == "SPY"
    assert list_payload[0]["summary_metrics"]["holdout"]["regression"]["mae"] == 1.234

    detail_response = client.get(f"/daily-index-forecast-models/{group_id}")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["feature_run"]["symbol"] == "SPY"
    assert detail_payload["feature_run"]["benchmark_symbol"] == "QQQ"
    assert detail_payload["feature_run"]["decision_times"] == ["09:45"]
    assert detail_payload["dataset_manifest"]["feature_rows"] == 9
    assert detail_payload["targets"][0]["target_key"] == "regression"

    status_response = client.get(f"/daily-index-forecast-models/{group_id}/status")
    assert status_response.status_code == 200
    status_payload = status_response.json()
    assert status_payload["argo_phase"] == "Running"
    assert status_payload["progress_pct"] == 25.0

    workflow_errors_response = client.get(f"/daily-index-forecast-models/{group_id}/workflow-errors")
    assert workflow_errors_response.status_code == 200
    workflow_errors_payload = workflow_errors_response.json()
    assert workflow_errors_payload["available"] is True
    assert workflow_errors_payload["error_exception"] == "ValueError: boom"
    assert workflow_errors_payload["error_call_stack"] == ["train.py:42", "pipeline.py:88"]

    retry_response = client.post(f"/daily-index-forecast-models/{group_id}/retry")
    assert retry_response.status_code == 202
    retry_payload = retry_response.json()
    assert retry_payload["group_id"] != group_id
    assert retry_payload["feature_run_id"] != feature_run_id

    delete_response = client.delete(f"/daily-index-forecast-models/{group_id}")
    assert delete_response.status_code == 204
    assert client.get(f"/daily-index-forecast-models/{group_id}").status_code == 404
