from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import pytest

from datetime import UTC, datetime

from app.db.models import BacktestJob
from app.db.models import RiskModelGroup
from app.db.models import RiskModelSource
from app.db.models import RiskModelTarget
from app.db.session import get_db_session

from tests.conftest import build_backtest_client


def _insert_backtest_job(
    session,
    backtest_id: str,
    *,
    labels_path: str,
    features_path: str,
    selection: dict | None = None,
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
            selection=selection,
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


def _insert_risk_model_group(
    session,
    *,
    group_id: str,
    backtest_ids: list[str],
    name: str | None = None,
) -> None:
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id=group_id,
            status="running",
            argo_namespace=None,
            argo_workflow_name=None,
            name=name,
            params_json={"backtest_ids": backtest_ids, "targets": [], "dataset_config": {}, "train_config": {}},
            artifact_dir=f"/tmp/risk-models/{group_id}",
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


def test_risk_models_list_empty(tmp_path) -> None:
    client = build_backtest_client(tmp_path)
    response = client.get("/risk-models")
    assert response.status_code == 200
    assert response.json() == []


def test_risk_models_show_training_date_range(tmp_path) -> None:
    client = build_backtest_client(tmp_path)

    labels_path = tmp_path / "labels.parquet"
    feats_path = tmp_path / "features.parquet"
    pd.DataFrame([{"candidate_id": "c1", "label_hit_stop": 0, "label_mae": 0.1}]).to_parquet(
        labels_path,
        index=False,
    )
    pd.DataFrame([{"candidate_id": "c1", "f1": 1.0}]).to_parquet(feats_path, index=False)

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    _insert_backtest_job(
        session,
        "b1",
        labels_path=str(labels_path),
        features_path=str(feats_path),
        selection={
            "start_date": "2024-01-05",
            "end_date": "2024-01-10",
            "resolution": "1d",
            "feed": "iex",
            "symbols": ["AAPL"],
            "triggers": ["sma_cross"],
            "exit_rules": ["basic"],
        },
    )
    _insert_backtest_job(
        session,
        "b2",
        labels_path=str(labels_path),
        features_path=str(feats_path),
        selection={
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
            "resolution": "1d",
            "feed": "iex",
            "symbols": ["AAPL"],
            "triggers": ["sma_cross"],
            "exit_rules": ["basic"],
        },
    )
    _insert_risk_model_group(session, group_id="g-1", backtest_ids=["b1", "b2"])
    session.commit()
    session.close()

    list_response = client.get("/risk-models")
    assert list_response.status_code == 200
    list_payload = list_response.json()
    assert list_payload[0]["training_start_date"] == "2024-01-01"
    assert list_payload[0]["training_end_date"] == "2024-01-10"

    detail_response = client.get("/risk-models/g-1")
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["training_start_date"] == "2024-01-01"
    assert detail_payload["training_end_date"] == "2024-01-10"


def test_risk_models_can_rename_existing_model(tmp_path) -> None:
    client = build_backtest_client(tmp_path)

    labels_path = tmp_path / "labels.parquet"
    feats_path = tmp_path / "features.parquet"
    pd.DataFrame([{"candidate_id": "c1", "label_hit_stop": 0, "label_mae": 0.1}]).to_parquet(
        labels_path,
        index=False,
    )
    pd.DataFrame([{"candidate_id": "c1", "f1": 1.0}]).to_parquet(feats_path, index=False)

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    _insert_backtest_job(session, "b1", labels_path=str(labels_path), features_path=str(feats_path))
    _insert_risk_model_group(session, group_id="g-1", backtest_ids=["b1"], name="Original Name")
    session.commit()
    session.close()

    response = client.patch("/risk-models/g-1", json={"name": "Renamed Model"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Renamed Model"
    assert payload["params"]["name"] == "Renamed Model"

    list_response = client.get("/risk-models")
    assert list_response.status_code == 200
    assert list_response.json()[0]["name"] == "Renamed Model"

    clear_response = client.patch("/risk-models/g-1", json={"name": None})
    assert clear_response.status_code == 200
    clear_payload = clear_response.json()
    assert clear_payload["name"] is None
    assert "name" not in clear_payload["params"]


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


def test_risk_models_retry_creates_new_group_from_failed_model(tmp_path, monkeypatch) -> None:
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
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id="g1",
            status="failed",
            argo_namespace="ns",
            argo_workflow_name="wf",
            params_json={
                "requested_at": now.isoformat(),
                "backtest_ids": ["b1"],
                "targets": [{"target_key": "stop_prob", "task_type": "classification"}],
                "dataset_config": {},
                "train_config": {"random_seed": 7},
            },
            artifact_dir=str(tmp_path / "risk-artifacts" / "g1"),
            summary_metrics_json=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(RiskModelSource(group_id="g1", backtest_id="b1", source_report_path=None))
    session.commit()
    session.close()

    monkeypatch.setenv("BACKTEST_ARGO_ENABLED", "0")
    monkeypatch.setenv("ARGO_SERVER_URL", "")
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", str(tmp_path / "shared-results"))

    response = client.post("/risk-models/g1/retry")
    assert response.status_code in {202, 503}

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    groups = session.query(RiskModelGroup).order_by(RiskModelGroup.created_at.asc()).all()
    assert len(groups) == 2
    assert groups[-1].id != "g1"
    assert groups[-1].params_json["backtest_ids"] == ["b1"]
    assert groups[-1].params_json["train_config"] == {"random_seed": 7}
    session.close()


def test_risk_models_delete_removes_db_rows_and_artifacts(tmp_path, monkeypatch) -> None:
    client = build_backtest_client(tmp_path)

    # Avoid any Argo HTTP calls inside delete().
    monkeypatch.setenv("BACKTEST_ARGO_ENABLED", "0")
    monkeypatch.setenv("ARGO_SERVER_URL", "")

    artifact_dir = tmp_path / "risk-artifacts" / "g1"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "dummy.txt").write_text("x", encoding="utf-8")

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id="g1",
            status="running",
            argo_namespace="ns",
            argo_workflow_name="wf",
            params_json={},
            artifact_dir=str(artifact_dir),
            summary_metrics_json=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(RiskModelSource(group_id="g1", backtest_id="b1", source_report_path=None))
    session.add(
        RiskModelTarget(
            group_id="g1",
            target_key="t1",
            task_type="classification",
            status="running",
            model_artifact_path=None,
            metrics_json=None,
            dataset_manifest_path=None,
            feature_columns_json=None,
        )
    )
    session.commit()
    session.close()

    response = client.delete("/risk-models/g1")
    assert response.status_code == 204
    assert not artifact_dir.exists()

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    assert session.get(RiskModelGroup, "g1") is None
    assert session.query(RiskModelSource).filter(RiskModelSource.group_id == "g1").count() == 0
    assert session.query(RiskModelTarget).filter(RiskModelTarget.group_id == "g1").count() == 0
    session.close()


def test_risk_models_list_includes_progress_counts(tmp_path) -> None:
    client = build_backtest_client(tmp_path)

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id="g1",
            status="running",
            argo_namespace=None,
            argo_workflow_name=None,
            params_json={},
            artifact_dir=str(tmp_path / "g1"),
            summary_metrics_json=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(
        RiskModelTarget(
            group_id="g1",
            target_key="t1",
            task_type="classification",
            status="running",
            model_artifact_path=None,
            metrics_json=None,
            dataset_manifest_path=None,
            feature_columns_json=None,
        )
    )
    session.add(
        RiskModelTarget(
            group_id="g1",
            target_key="t2",
            task_type="classification",
            status="succeeded",
            model_artifact_path=None,
            metrics_json=None,
            dataset_manifest_path=None,
            feature_columns_json=None,
        )
    )
    session.commit()
    session.close()

    response = client.get("/risk-models")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    item = payload[0]
    assert item["group_id"] == "g1"
    assert item["targets_total"] == 2
    assert item["targets_done"] == 1


def test_risk_model_detail_includes_dataset_manifest_summary(tmp_path) -> None:
    client = build_backtest_client(tmp_path)

    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-01T12:00:00.000Z",
                "dataset_version": "risk_dataset_v1",
                "label_version": "labels_v1",
                "feature_version": "features_v1",
                "config_hash": "abc123def4567890",
                "source_report_paths": ["/tmp/report-a.json", "/tmp/report-b.json"],
                "total_candidates": 18,
                "labeled_rows": 16,
                "feature_rows": 17,
                "joined_rows": 15,
                "dropped_label_rows": 2,
                "dropped_feature_rows": 1,
                "duplicate_candidate_ids": 3,
                "output_path": "/tmp/risk-models/g1/dataset/dataset.parquet",
            }
        ),
        encoding="utf-8",
    )

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id="g1",
            status="succeeded",
            argo_namespace="ns",
            argo_workflow_name="wf",
            params_json={"backtest_ids": ["b1"], "train_config": {"random_seed": 7}},
            artifact_dir=str(tmp_path / "risk-artifacts" / "g1"),
            summary_metrics_json={"stop_prob": {"auc_calibrated": 0.77}},
            created_at=now,
            updated_at=now,
        )
    )
    session.add(RiskModelSource(group_id="g1", backtest_id="b1", source_report_path="/tmp/report-a.json"))
    session.add(
        RiskModelTarget(
            group_id="g1",
            target_key="stop_prob",
            task_type="classification",
            status="succeeded",
            model_artifact_path="/tmp/risk-models/g1/targets/stop_prob/model.json",
            metrics_json={"auc_calibrated": 0.77},
            dataset_manifest_path=str(manifest_path),
            feature_columns_json=["f1", "f2"],
        )
    )
    session.commit()
    session.close()

    response = client.get("/risk-models/g1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["group_id"] == "g1"
    assert payload["dataset_manifest"]["total_candidates"] == 18
    assert payload["dataset_manifest"]["joined_rows"] == 15
    assert payload["dataset_manifest"]["source_report_paths"] == ["/tmp/report-a.json", "/tmp/report-b.json"]
    assert payload["targets"][0]["dataset_manifest_path"] == str(manifest_path)


def test_risk_model_detail_omits_dataset_manifest_when_missing(tmp_path) -> None:
    client = build_backtest_client(tmp_path)

    session_gen = client.app.dependency_overrides[get_db_session]()  # type: ignore[misc]
    session = next(session_gen)
    now = datetime.now(UTC)
    session.add(
        RiskModelGroup(
            id="g1",
            status="succeeded",
            argo_namespace=None,
            argo_workflow_name=None,
            params_json={},
            artifact_dir=str(tmp_path / "risk-artifacts" / "g1"),
            summary_metrics_json=None,
            created_at=now,
            updated_at=now,
        )
    )
    session.add(RiskModelTarget(
        group_id="g1",
        target_key="stop_prob",
        task_type="classification",
        status="succeeded",
        model_artifact_path=None,
        metrics_json=None,
        dataset_manifest_path=str(tmp_path / "missing-manifest.json"),
        feature_columns_json=None,
    ))
    session.commit()
    session.close()

    response = client.get("/risk-models/g1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["dataset_manifest"] is None
