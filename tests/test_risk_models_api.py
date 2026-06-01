from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from datetime import UTC, datetime

from app.db.models import BacktestJob
from app.db.models import RiskModelGroup
from app.db.session import get_db_session

from tests.conftest import build_backtest_client


def _insert_backtest_job(session, backtest_id: str, *, labels_path: str, features_path: str) -> None:
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


def test_risk_models_list_empty(tmp_path) -> None:
    client = build_backtest_client(tmp_path)
    response = client.get("/risk-models")
    assert response.status_code == 200
    assert response.json() == []


def test_risk_models_create_validates_backtest_artifacts(tmp_path) -> None:
    client = build_backtest_client(tmp_path)

    response = client.post(
        "/risk-models",
        json={
            "backtest_ids": ["missing"],
            "targets": [],
            "dataset_config": {},
            "train_config": {},
        },
    )
    assert response.status_code == 422


def test_risk_models_create_accepts_backtest_with_parquets(tmp_path, monkeypatch) -> None:
    client = build_backtest_client(tmp_path)

    labels_path = tmp_path / "labels.parquet"
    feats_path = tmp_path / "features.parquet"
    pd.DataFrame(
        [
            {"candidate_id": "c1", "label_hit_stop": 0, "label_mae": 0.1},
            {"candidate_id": "c2", "label_hit_stop": 1, "label_mae": 0.2},
        ]
    ).to_parquet(labels_path, index=False)
    pd.DataFrame(
        [
            {"candidate_id": "c1", "f1": 1.0},
            {"candidate_id": "c2", "f1": 2.0},
        ]
    ).to_parquet(feats_path, index=False)

    # Insert row directly via the overridden DB session dependency.
    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    _insert_backtest_job(session, "b1", labels_path=str(labels_path), features_path=str(feats_path))
    session.commit()
    session.close()

    # Prevent real Argo submission in this unit test.
    monkeypatch.setenv("BACKTEST_ARGO_ENABLED", "0")
    monkeypatch.setenv("ARGO_SERVER_URL", "")
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", str(tmp_path / "shared-results"))

    response = client.post(
        "/risk-models",
        json={
            "backtest_ids": ["b1"],
            "targets": [
                {"target_key": "stop_prob", "task_type": "classification"},
                {"target_key": "mae", "task_type": "regression"},
            ],
            "dataset_config": {},
            "train_config": {"random_seed": 7},
        },
    )
    # When Argo is not configured, the API returns 503.
    assert response.status_code in {202, 503}


def test_risk_models_create_skips_local_writes_when_artifact_dir_unwritable(tmp_path, monkeypatch) -> None:
    client = build_backtest_client(tmp_path)

    labels_path = tmp_path / "labels.parquet"
    feats_path = tmp_path / "features.parquet"
    pd.DataFrame(
        [
            {"candidate_id": "c1", "label_hit_stop": 0, "label_mae": 0.1},
        ]
    ).to_parquet(labels_path, index=False)
    pd.DataFrame([{"candidate_id": "c1", "f1": 1.0}]).to_parquet(feats_path, index=False)

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    _insert_backtest_job(session, "b1", labels_path=str(labels_path), features_path=str(feats_path))
    session.commit()
    session.close()

    # Unwritable mount to simulate out-of-cluster /data PVC path.
    unwritable_mount = tmp_path / "unwritable-results"
    unwritable_mount.mkdir()
    unwritable_mount.chmod(0o555)

    monkeypatch.setenv("BACKTEST_ARGO_ENABLED", "0")
    monkeypatch.setenv("ARGO_SERVER_URL", "")
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", str(unwritable_mount))

    response = client.post(
        "/risk-models",
        json={
            "backtest_ids": ["b1"],
            "targets": [
                {"target_key": "stop_prob", "task_type": "classification"},
            ],
            "dataset_config": {},
            "train_config": {},
        },
    )
    assert response.status_code in {202, 503}

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    group = session.query(RiskModelGroup).order_by(RiskModelGroup.created_at.desc()).first()
    assert group is not None
    # params.json is skipped because artifact_dir isn't writable locally
    assert not Path(group.artifact_dir, "params.json").exists()
    session.close()


def test_risk_models_create_writes_params_json_when_artifact_dir_writable(tmp_path, monkeypatch) -> None:
    client = build_backtest_client(tmp_path)

    labels_path = tmp_path / "labels.parquet"
    feats_path = tmp_path / "features.parquet"
    pd.DataFrame(
        [
            {"candidate_id": "c1", "label_hit_stop": 0, "label_mae": 0.1},
        ]
    ).to_parquet(labels_path, index=False)
    pd.DataFrame([{"candidate_id": "c1", "f1": 1.0}]).to_parquet(feats_path, index=False)

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    _insert_backtest_job(session, "b1", labels_path=str(labels_path), features_path=str(feats_path))
    session.commit()
    session.close()

    writable_mount = tmp_path / "writable-results"
    writable_mount.mkdir()

    monkeypatch.setenv("BACKTEST_ARGO_ENABLED", "0")
    monkeypatch.setenv("ARGO_SERVER_URL", "")
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", str(writable_mount))

    response = client.post(
        "/risk-models",
        json={
            "backtest_ids": ["b1"],
            "targets": [
                {"target_key": "stop_prob", "task_type": "classification"},
            ],
            "dataset_config": {},
            "train_config": {},
        },
    )
    assert response.status_code in {202, 503}

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    group = session.query(RiskModelGroup).order_by(RiskModelGroup.created_at.desc()).first()
    assert group is not None
    assert Path(group.artifact_dir, "params.json").exists()
    session.close()
