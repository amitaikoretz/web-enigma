from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from app.db.models import BacktestJob, RiskModelGroup, RiskModelSource
from app.db.session import get_db_session

from tests.conftest import build_backtest_client


def _insert_backtest_job(
    session,
    backtest_id: str,
    *,
    labels_path: str,
    features_path: str,
) -> None:
    now = datetime.now(UTC)
    session.add(
        BacktestJob(
            id=backtest_id,
            name="test",
            created_at=now,
            updated_at=now,
            status="completed",
            report_status="success",
            total_runs=1,
            completed_runs=1,
            successful_runs=1,
            failed_runs=0,
            selection=None,
            error_message=None,
            execution_backend="local",
            workflow_name=None,
            workflow_namespace=None,
            started_at=None,
            finished_at=None,
            config_path=None,
            report_json_path=None,
            report_parquet_path=None,
            candidates_json_path=None,
            candidates_parquet_path=None,
            equity_parquet_path=None,
            orders_parquet_path=None,
            trades_parquet_path=None,
            rejections_parquet_path=None,
            labels_parquet_path=labels_path,
            features_parquet_path=features_path,
            manifest_path=None,
        )
    )


def _insert_model_group(
    session,
    *,
    group_id: str,
    family: str,
    backtest_ids: list[str],
) -> None:
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id=group_id,
            family=family,
            status="running",
            argo_namespace=None,
            argo_workflow_name=None,
            params_json={"backtest_ids": backtest_ids, "targets": [], "dataset_config": {}, "train_config": {}},
            artifact_dir=f"/tmp/{family}/{group_id}",
            summary_metrics_json=None,
            created_at=now,
            updated_at=now,
        )
    )
    for backtest_id in backtest_ids:
        session.add(
            RiskModelSource(
                group_id=group_id,
                backtest_id=backtest_id,
                source_report_path=None,
            )
        )


def test_return_forecast_models_list_filters_family(tmp_path) -> None:
    client = build_backtest_client(tmp_path)

    labels_path = tmp_path / "labels.parquet"
    features_path = tmp_path / "features.parquet"
    pd.DataFrame([{"candidate_id": "c1", "label_hit_stop": 0, "label_mae": 0.1}]).to_parquet(
        labels_path,
        index=False,
    )
    pd.DataFrame([{"candidate_id": "c1", "f1": 1.0}]).to_parquet(features_path, index=False)

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    _insert_backtest_job(session, "b-risk", labels_path=str(labels_path), features_path=str(features_path))
    _insert_backtest_job(session, "b-return", labels_path=str(labels_path), features_path=str(features_path))
    _insert_model_group(session, group_id="risk-1", family="risk", backtest_ids=["b-risk"])
    _insert_model_group(session, group_id="return-1", family="return_forecast", backtest_ids=["b-return"])
    session.commit()
    session.close()

    risk_response = client.get("/risk-models")
    assert risk_response.status_code == 200
    assert [item["group_id"] for item in risk_response.json()] == ["risk-1"]

    return_response = client.get("/return-forecast-models")
    assert return_response.status_code == 200
    assert [item["group_id"] for item in return_response.json()] == ["return-1"]


def test_return_forecast_models_create_validates_backtest_artifacts(tmp_path) -> None:
    client = build_backtest_client(tmp_path)

    response = client.post(
        "/return-forecast-models",
        json={
            "backtest_ids": ["missing"],
            "targets": [],
            "dataset_config": {},
            "train_config": {},
        },
    )
    assert response.status_code == 422
