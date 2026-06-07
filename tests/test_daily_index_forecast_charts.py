from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.factory import create_app
from app.api.routes import daily_index_forecast_models as route_module
from app.daily_index_forecast import features as features_module
from app.daily_index_forecast import charts as charts_module
from app.config.models import DataCacheConfig
from app.daily_index_forecast.models import DailyIndexForecastDatasetManifestSummary
from app.daily_index_forecast.persistence import SqlAlchemyDailyIndexForecastRepository
from app.daily_index_forecast.records import DailyIndexModelArtifact
from app.db.base import Base
from app.db.session import get_db_session


def _build_client(tmp_path) -> tuple[TestClient, sessionmaker[Session]]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    app = create_app(
        cache_config=DataCacheConfig(directory=str(tmp_path / "cache")),
        output_dir=tmp_path / "api-results",
        log_file=tmp_path / "api.log",
        session_factory=test_session_factory,
    )

    def override_db_session():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db_session
    return TestClient(app), test_session_factory


def _seed_daily_index_model(tmp_path, session_factory, *, params: dict | None = None, model_features: list[str] | None = None):
    manifest_dir = tmp_path / "artifacts"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = manifest_dir / "dataset.parquet"
    manifest_path = manifest_dir / "manifest.json"
    model_path = manifest_dir / "model.json"

    frame = pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "session_date": date(2024, 1, 3),
                "decision_time": "09:45",
                "decision_timestamp": datetime(2024, 1, 3, 14, 45, tzinfo=UTC),
                "return_to_close_bps": 12.5,
                "net_return_after_cost_bps": 9.5,
                "positive_after_cost": True,
                "feature_one": 1.0,
                "feature_two": 2.0,
            },
            {
                "symbol": "SPY",
                "session_date": date(2024, 1, 3),
                "decision_time": "10:30",
                "decision_timestamp": datetime(2024, 1, 3, 15, 30, tzinfo=UTC),
                "return_to_close_bps": -4.0,
                "net_return_after_cost_bps": -7.0,
                "positive_after_cost": False,
                "feature_one": 3.0,
                "feature_two": 4.0,
            },
        ]
    )
    frame.to_parquet(dataset_path, index=False)

    manifest = DailyIndexForecastDatasetManifestSummary(
        generated_at=datetime(2024, 1, 4, tzinfo=UTC),
        dataset_version="1",
        feature_version="1",
        label_version="1",
        model_version="1",
        config_hash="abc",
        symbol_count=1,
        benchmark_symbol="QQQ",
        start_date=date(2024, 1, 3),
        end_date=date(2024, 1, 3),
        decision_times=["09:45", "10:30"],
        total_source_rows=2,
        feature_rows=2,
        label_rows=2,
        joined_rows=2,
        dropped_feature_rows=0,
        dropped_label_rows=0,
        output_path=str(dataset_path),
        features_path=str(dataset_path),
        labels_path=str(dataset_path),
        feature_columns=["feature_one", "feature_two"],
    )
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")

    model_features = model_features or ["feature_one", "feature_two"]
    artifact = DailyIndexModelArtifact(
        model_version="1",
        feature_version="1",
        label_version="1",
        dataset_version="1",
        feature_run_id="fr-1",
        selected_fold_id=1,
        selected_alpha=1.0,
        selected_features=model_features,
        scaler_mean=[0.0, 0.0],
        scaler_scale=[1.0, 1.0],
        coefficients=[2.0, 3.0],
        intercept=1.5,
        residual_std=1.0,
        costs={"spread_bps": 1.0},
        walk_forward={"holdout_start": "2024-01-10T00:00:00Z"},
        holdout_metrics={},
        aggregate_metrics={},
    )
    model_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")

    repo = SqlAlchemyDailyIndexForecastRepository(session_factory)
    params = params or {
        "universe": {
            "start_date": "2024-01-03",
            "end_date": "2024-01-03",
            "decision_times": ["09:45", "10:30"],
            "symbols": [
                {
                    "symbol": "SPY",
                    "data": {"type": "alpaca", "symbol": "SPY", "interval": "5m", "feed": "iex"},
                }
            ],
            "benchmark": None,
        },
        "feature_config": {
            "opening_window_minutes": 15,
            "rolling_sessions": [5, 20],
            "benchmark_sessions": [5, 20],
            "use_calendar_features": True,
            "use_cross_market_features": True,
        },
        "walk_forward": {
            "train_days": 1,
            "validation_days": 1,
            "test_days": 1,
            "step_days": 1,
            "embargo_days": 0,
            "holdout_days": 1,
            "min_train_rows": 1,
            "min_validation_rows": 1,
            "min_test_rows": 1,
            "min_holdout_rows": 1,
        },
        "train_config": {"alpha_grid": [1.0], "residual_distribution": "normal", "random_seed": 7},
        "costs": {"spread_bps": 1.0, "slippage_bps": 1.0, "impact_bps": 0.5},
        "data_cache": {"directory": str(tmp_path / "cache")},
    }
    with session_factory() as session:
        repo.create_feature_run(
            feature_run_id="fr-1",
            symbol="SPY",
            benchmark_symbol="QQQ",
            decision_times=["09:45", "10:30"],
            start_date=date(2024, 1, 3),
            end_date=date(2024, 1, 3),
            status="succeeded",
            params=params,
            artifact_dir=str(manifest_dir),
            manifest_path=str(manifest_path),
            features_parquet_path=str(dataset_path),
            labels_parquet_path=str(dataset_path),
            summary_metrics={},
            argo_namespace="ns",
            argo_workflow_name="wf",
        )
        repo.create_group(
            group_id="di-1",
            feature_run_id="fr-1",
            name="Daily Index",
            status="succeeded",
            params=params,
            artifact_dir=str(manifest_dir),
            argo_namespace="ns",
            argo_workflow_name="wf",
        )
        repo.upsert_target(
            group_id="di-1",
            target_key="daily_index_forecast",
            task_type="regression",
            status="succeeded",
            model_artifact_path=str(model_path),
            metrics={
                "fold_metrics": [
                    {
                        "train_start": "2024-01-01T00:00:00Z",
                        "train_end": "2024-01-03T14:00:00Z",
                        "validation_start": "2024-01-03T14:00:00Z",
                        "validation_end": "2024-01-03T15:00:00Z",
                        "test_start": "2024-01-03T15:00:00Z",
                        "test_end": "2024-01-04T00:00:00Z",
                    }
                ]
            },
            dataset_manifest_path=str(manifest_path),
            feature_columns=["feature_one", "feature_two"],
        )

    return str(model_path), str(manifest_path)


def test_daily_index_forecast_chart_data_returns_bars_and_predictions(tmp_path, monkeypatch):
    client, session_factory = _build_client(tmp_path)
    _seed_daily_index_model(tmp_path, session_factory)

    def fake_loader(universe, cache_config, force_refresh=False):
        frame = pd.DataFrame(
            [
                {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000},
            ],
            index=pd.DatetimeIndex([pd.Timestamp("2024-01-03T14:30:00Z")]),
        )
        return {"SPY": frame}, None

    monkeypatch.setattr(charts_module, "load_universe_frames", fake_loader)
    monkeypatch.setattr(features_module, "load_universe_frames", fake_loader)

    response = client.get("/daily-index-forecast-models/di-1/chart-data?selected_date=2024-01-03&resolution=5m")
    assert response.status_code == 200
    body = response.json()
    assert body["group_id"] == "di-1"
    assert body["source"] == "stored"
    assert body["split_label"] == "validation"
    assert body["bars"]["rows"][0]["timestamp"] == "2024-01-03T14:30:00+00:00"
    assert body["predictions"][0]["predicted_bps"] == 1.5 + (1.0 * 2.0) + (2.0 * 3.0)
    assert body["predictions"][0]["split_label"] == "validation"


def test_daily_index_forecast_chart_data_computes_missing_rows(tmp_path, monkeypatch):
    client, session_factory = _build_client(tmp_path)
    params = {
        "universe": {
            "start_date": "2024-01-03",
            "end_date": "2024-01-04",
            "decision_times": ["09:45"],
            "symbols": [
                {
                    "symbol": "SPY",
                    "data": {"type": "alpaca", "symbol": "SPY", "interval": "5m", "feed": "iex"},
                }
            ],
            "benchmark": None,
        },
        "feature_config": {
            "opening_window_minutes": 15,
            "rolling_sessions": [5, 20],
            "benchmark_sessions": [5, 20],
            "use_calendar_features": True,
            "use_cross_market_features": True,
        },
        "walk_forward": {
            "train_days": 1,
            "validation_days": 1,
            "test_days": 1,
            "step_days": 1,
            "embargo_days": 0,
            "holdout_days": 1,
            "min_train_rows": 1,
            "min_validation_rows": 1,
            "min_test_rows": 1,
            "min_holdout_rows": 1,
        },
        "train_config": {"alpha_grid": [1.0], "residual_distribution": "normal", "random_seed": 7},
        "costs": {"spread_bps": 1.0, "slippage_bps": 1.0, "impact_bps": 0.5},
        "data_cache": {"directory": str(tmp_path / "cache")},
    }
    _seed_daily_index_model(
        tmp_path,
        session_factory,
        params=params,
        model_features=["bars_seen", "opening_window_minutes"],
    )
    computed_frame = pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "session_date": date(2024, 1, 5),
                "decision_time": "09:45",
                "decision_timestamp": datetime(2024, 1, 5, 14, 45, tzinfo=UTC),
                "return_to_close_bps": 5.0,
                "bars_seen": 2.0,
                "opening_window_minutes": 15.0,
            }
        ]
    )
    fake_artifact = DailyIndexModelArtifact(
        model_version="1",
        feature_version="1",
        label_version="1",
        dataset_version="1",
        feature_run_id="chart-view",
        selected_fold_id=1,
        selected_alpha=1.0,
        selected_features=["bars_seen", "opening_window_minutes"],
        scaler_mean=[0.0, 0.0],
        scaler_scale=[1.0, 1.0],
        coefficients=[1.0, 1.0],
        intercept=0.5,
        residual_std=1.0,
        costs={"spread_bps": 1.0},
        walk_forward={"holdout_start": "2024-01-10T00:00:00Z"},
        holdout_metrics={},
        aggregate_metrics={},
    )
    fake_manifest = DailyIndexForecastDatasetManifestSummary(
        generated_at=datetime(2024, 1, 5, tzinfo=UTC),
        dataset_version="1",
        feature_version="1",
        label_version="1",
        model_version="1",
        config_hash="abc",
        symbol_count=1,
        benchmark_symbol=None,
        start_date=date(2024, 1, 3),
        end_date=date(2024, 1, 5),
        decision_times=["09:45"],
        total_source_rows=2,
        feature_rows=1,
        label_rows=1,
        joined_rows=1,
        dropped_feature_rows=0,
        dropped_label_rows=0,
        output_path=str(tmp_path / "computed.parquet"),
        features_path=str(tmp_path / "computed.parquet"),
        labels_path=str(tmp_path / "computed.parquet"),
        feature_columns=["bars_seen", "opening_window_minutes"],
    )
    monkeypatch.setattr(
        charts_module,
        "build_dataset_frames",
        lambda universe, feature_config, costs, data_cache, force_refresh=False: (
            computed_frame,
            computed_frame,
            computed_frame,
            fake_manifest,
            ["bars_seen", "opening_window_minutes"],
        ),
    )
    monkeypatch.setattr(
        charts_module,
        "train_daily_index_model",
        lambda dataset, group_id, feature_run_id, train_config, walk_forward, costs, feature_columns: (
            fake_artifact,
            {"fold_metrics": [
                {
                    "train_start": "2024-01-01T00:00:00Z",
                    "train_end": "2024-01-05T14:00:00Z",
                    "validation_start": "2024-01-05T14:00:00Z",
                    "validation_end": "2024-01-05T15:00:00Z",
                    "test_start": "2024-01-05T15:00:00Z",
                    "test_end": "2024-01-06T00:00:00Z",
                }
            ]},
            [],
        ),
    )
    monkeypatch.setattr(
        charts_module,
        "load_universe_frames",
        lambda universe, cache_config, force_refresh=False: (
            {
                "SPY": pd.DataFrame(
                    [
                        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000},
                        {"Open": 100.5, "High": 102.0, "Low": 100.0, "Close": 101.5, "Volume": 1200},
                    ],
                    index=pd.DatetimeIndex([
                        pd.Timestamp("2024-01-05T14:30:00Z"),
                        pd.Timestamp("2024-01-05T14:35:00Z"),
                    ]),
                )
            },
            None,
        ),
    )
    monkeypatch.setattr(features_module, "load_universe_frames", lambda universe, cache_config, force_refresh=False: (
        {
            "SPY": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000},
                    {"Open": 100.5, "High": 102.0, "Low": 100.0, "Close": 101.5, "Volume": 1200},
                    {"Open": 101.5, "High": 103.0, "Low": 101.0, "Close": 102.5, "Volume": 1400},
                ],
                index=pd.DatetimeIndex([
                    pd.Timestamp("2024-01-05T14:30:00Z"),
                    pd.Timestamp("2024-01-05T14:35:00Z"),
                    pd.Timestamp("2024-01-05T14:50:00Z"),
                ]),
            )
        },
        None,
    ))
    monkeypatch.setattr(
        charts_module,
        "build_feature_and_label_records",
        lambda universe, feature_config, costs, data_cache, force_refresh=False: (
            [
                features_module.DailyIndexFeatureRecord(
                    symbol="SPY",
                    session_date=date(2024, 1, 5),
                    decision_time="09:45",
                    decision_timestamp=datetime(2024, 1, 5, 14, 45, tzinfo=UTC),
                    session_open_timestamp=datetime(2024, 1, 5, 14, 30, tzinfo=UTC),
                    session_close_timestamp=datetime(2024, 1, 5, 21, 0, tzinfo=UTC),
                    bars_seen=3,
                    opening_window_minutes=15,
                    open_price=100.0,
                    high_price=103.0,
                    low_price=99.0,
                    last_price=102.5,
                    volume_so_far=3600.0,
                    dollar_volume_so_far=3700.0,
                    day_of_week=4,
                    month=1,
                    is_month_start=False,
                    is_month_end=False,
                    minutes_since_open=15,
                    minutes_to_close=375,
                )
            ],
            [],
            {"generated_at": datetime(2024, 1, 5, tzinfo=UTC), "dataset_version": "1"},
        ),
    )

    response = client.get("/daily-index-forecast-models/di-1/chart-data?selected_date=2024-01-05&resolution=5m")
    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "computed"
    assert body["predictions"]


def test_daily_index_forecast_chart_data_rejects_missing_market_data(tmp_path, monkeypatch):
    client, session_factory = _build_client(tmp_path)
    params = {
        "universe": {
            "start_date": "2024-01-03",
            "end_date": "2024-01-04",
            "decision_times": ["09:45"],
            "symbols": [
                {
                    "symbol": "SPY",
                    "data": {"type": "alpaca", "symbol": "SPY", "interval": "5m", "feed": "iex"},
                }
            ],
            "benchmark": None,
        },
        "feature_config": {
            "opening_window_minutes": 15,
            "rolling_sessions": [5, 20],
            "benchmark_sessions": [5, 20],
            "use_calendar_features": True,
            "use_cross_market_features": True,
        },
        "walk_forward": {
            "train_days": 1,
            "validation_days": 1,
            "test_days": 1,
            "step_days": 1,
            "embargo_days": 0,
            "holdout_days": 1,
            "min_train_rows": 1,
            "min_validation_rows": 1,
            "min_test_rows": 1,
            "min_holdout_rows": 1,
        },
        "train_config": {"alpha_grid": [1.0], "residual_distribution": "normal", "random_seed": 7},
        "costs": {"spread_bps": 1.0, "slippage_bps": 1.0, "impact_bps": 0.5},
        "data_cache": {"directory": str(tmp_path / "cache")},
    }
    _seed_daily_index_model(
        tmp_path,
        session_factory,
        params=params,
        model_features=["bars_seen", "opening_window_minutes"],
    )
    monkeypatch.setattr(
        charts_module,
        "load_universe_frames",
        lambda universe, cache_config, force_refresh=False: (
            {"SPY": pd.DataFrame([], columns=["Open", "High", "Low", "Close", "Volume"])},
            None,
        ),
    )
    monkeypatch.setattr(features_module, "load_universe_frames", lambda universe, cache_config, force_refresh=False: (
        {"SPY": pd.DataFrame([], columns=["Open", "High", "Low", "Close", "Volume"])},
        None,
    ))

    response = client.get("/daily-index-forecast-models/di-1/chart-data?selected_date=2024-01-05&resolution=5m")
    assert response.status_code == 422


def test_daily_index_forecast_chart_data_falls_back_to_group_artifact_dir(tmp_path, monkeypatch):
    client, session_factory = _build_client(tmp_path)
    manifest_dir = tmp_path / "results" / "daily-index-forecast-models" / "di-1"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = manifest_dir / "dataset.parquet"
    manifest_path = manifest_dir / "manifest.json"
    model_path = manifest_dir / "model.json"

    frame = pd.DataFrame(
        [
            {
                "symbol": "SPY",
                "session_date": date(2024, 1, 4),
                "decision_time": "09:45",
                "decision_timestamp": datetime(2024, 1, 4, 14, 45, tzinfo=UTC),
                "return_to_close_bps": 7.5,
                "net_return_after_cost_bps": 4.5,
                "positive_after_cost": True,
                "feature_one": 1.0,
                "feature_two": 2.0,
            }
        ]
    )
    frame.to_parquet(dataset_path, index=False)
    manifest = DailyIndexForecastDatasetManifestSummary(
        generated_at=datetime(2024, 1, 4, tzinfo=UTC),
        dataset_version="1",
        feature_version="1",
        label_version="1",
        model_version="1",
        config_hash="abc",
        symbol_count=1,
        benchmark_symbol="QQQ",
        start_date=date(2024, 1, 4),
        end_date=date(2024, 1, 4),
        decision_times=["09:45"],
        total_source_rows=1,
        feature_rows=1,
        label_rows=1,
        joined_rows=1,
        dropped_feature_rows=0,
        dropped_label_rows=0,
        output_path=str(dataset_path),
        features_path=str(dataset_path),
        labels_path=str(dataset_path),
        feature_columns=["feature_one", "feature_two"],
    )
    manifest_path.write_text(json.dumps(manifest.model_dump(mode="json")), encoding="utf-8")
    artifact = DailyIndexModelArtifact(
        model_version="1",
        feature_version="1",
        label_version="1",
        dataset_version="1",
        feature_run_id="fr-1",
        selected_fold_id=1,
        selected_alpha=1.0,
        selected_features=["feature_one", "feature_two"],
        scaler_mean=[0.0, 0.0],
        scaler_scale=[1.0, 1.0],
        coefficients=[1.0, 1.0],
        intercept=0.0,
        residual_std=1.0,
        costs={"spread_bps": 1.0},
        walk_forward={"holdout_start": "2024-01-10T00:00:00Z"},
        holdout_metrics={},
        aggregate_metrics={},
    )
    model_path.write_text(artifact.model_dump_json(indent=2), encoding="utf-8")

    repo = SqlAlchemyDailyIndexForecastRepository(session_factory)
    with session_factory() as session:
        repo.create_feature_run(
            feature_run_id="fr-1",
            symbol="SPY",
            benchmark_symbol="QQQ",
            decision_times=["09:45"],
            start_date=date(2024, 1, 4),
            end_date=date(2024, 1, 4),
            status="succeeded",
            params={
                "universe": {
                    "start_date": "2024-01-04",
                    "end_date": "2024-01-04",
                    "decision_times": ["09:45"],
                    "symbols": [{"symbol": "SPY", "data": {"type": "alpaca", "symbol": "SPY", "interval": "5m", "feed": "iex"}}],
                    "benchmark": None,
                },
                "feature_config": {"opening_window_minutes": 15, "rolling_sessions": [5, 20], "benchmark_sessions": [5, 20], "use_calendar_features": True, "use_cross_market_features": True},
                "walk_forward": {"train_days": 1, "validation_days": 1, "test_days": 1, "step_days": 1, "embargo_days": 0, "holdout_days": 1, "min_train_rows": 1, "min_validation_rows": 1, "min_test_rows": 1, "min_holdout_rows": 1},
                "train_config": {"alpha_grid": [1.0], "residual_distribution": "normal", "random_seed": 7},
                "costs": {"spread_bps": 1.0, "slippage_bps": 1.0, "impact_bps": 0.5},
                "data_cache": {"directory": str(tmp_path / "cache")},
            },
            artifact_dir=str(manifest_dir),
            manifest_path=str(manifest_path),
            features_parquet_path=str(dataset_path),
            labels_parquet_path=str(dataset_path),
            summary_metrics={},
            argo_namespace="ns",
            argo_workflow_name="wf",
        )
        repo.create_group(
            group_id="di-1",
            feature_run_id="fr-1",
            name="Daily Index",
            status="succeeded",
            params={},
            artifact_dir=str(manifest_dir),
            argo_namespace="ns",
            argo_workflow_name="wf",
        )
        repo.upsert_target(
            group_id="di-1",
            target_key="daily_index_forecast",
            task_type="regression",
            status="succeeded",
            model_artifact_path=str(tmp_path / "does-not-exist" / "model.json"),
            metrics={"fold_metrics": []},
            dataset_manifest_path=None,
            feature_columns=["feature_one", "feature_two"],
        )

    monkeypatch.setattr(
        charts_module,
        "load_universe_frames",
        lambda universe, cache_config, force_refresh=False: (
            {
                "SPY": pd.DataFrame(
                    [
                        {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000},
                    ],
                    index=pd.DatetimeIndex([pd.Timestamp("2024-01-04T14:30:00Z")]),
                )
            },
            None,
        ),
    )
    monkeypatch.setattr(features_module, "load_universe_frames", lambda universe, cache_config, force_refresh=False: (
        {
            "SPY": pd.DataFrame(
                [
                    {"Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.5, "Volume": 1000},
                ],
                index=pd.DatetimeIndex([pd.Timestamp("2024-01-04T14:30:00Z")]),
            )
        },
        None,
    ))

    response = client.get("/daily-index-forecast-models/di-1/chart-data?selected_date=2024-01-04&resolution=5m")
    assert response.status_code == 200
    assert response.json()["source"] == "stored"
