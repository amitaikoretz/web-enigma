from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from app.config.models import BacktestConfig
from app.engine.runner import run_backtests
from app.output.models import BacktestReport, CandidateRecord, FeatureSnapshotRecord, OutcomeLabelRecord, RunResult, RunSummary
from app.risk.data.report_loader import CandidateLoadError, load_candidates_from_reports
from app.risk.dataset import RiskDatasetReader
from app.risk.dataset.feature_columns import select_risk_feature_columns
from app.risk.dataset.builder import build_risk_dataset
from app.risk.models import RiskDatasetConfig, RiskDatasetManifest


def _write_candidate_report(path: Path, candidates: list[CandidateRecord]) -> None:
    report = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="test",
        input_config={
            "runs": [
                {
                    "run_id": "csv_candidates",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-19",
                    "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                    "strategy": "breakout_channel",
                    "strategy_params": {
                        "lookback": 3,
                        "stake": 1.0,
                        "stop_loss_pct": 0.01,
                        "take_profit_pct": 0.02,
                        "max_hold_bars": 5,
                    },
                    "analyzers": {"include_candidate_log": True},
                }
            ]
        },
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="csv_candidates",
                status="success",
                strategy="breakout_channel",
                symbol="TEST",
                data_source="csv",
                summary=RunSummary(
                    start_value=10_000.0,
                    end_value=10_100.0,
                    return_pct=1.0,
                    total_trades=1,
                    won_trades=1,
                    lost_trades=0,
                ),
                analyzers={"resolution": "1d", "candidate_diagnostics": {"total_candidates": len(candidates)}},
                candidates=candidates,
            )
        ],
    )
    path.write_text(report.model_dump_json(), encoding="utf-8")


def _make_split_sidecar_rows(
    *,
    run_id: str,
    row_count: int,
    blob_size: int,
) -> tuple[list[OutcomeLabelRecord], list[FeatureSnapshotRecord]]:
    labels: list[OutcomeLabelRecord] = []
    features: list[FeatureSnapshotRecord] = []
    for idx in range(row_count):
        candidate_id = f"{run_id}-{idx}"
        blob = "|".join(f"{run_id}-{idx}-{i:04d}" for i in range(blob_size))
        labels.append(
            OutcomeLabelRecord(
                candidate_id=candidate_id,
                label_version="labels_v1",
                entry_price=100.0 + idx,
                horizon_bars=5,
                stop_pct=0.03,
                target_pct=0.06,
                mae_pct=0.01,
                mae_abs_pct=0.01,
                mae_atr=None,
                mfe_pct=0.02,
                final_return_pct=0.01,
                realized_R=0.33,
                hit_stop=False,
                hit_target=False,
                hit_stop_before_target=True,
                bars_to_stop=None,
                bars_to_target=None,
                bars_held=5,
                exit_reason="TIME",
                label_quality_flag="OK",
            )
        )
        features.append(
            FeatureSnapshotRecord(
                candidate_id=candidate_id,
                feature_version="features_v1",
                feature_timestamp="2024-01-10T00:00:00+00:00",
                feature_quality_flag="OK",
                return_20=0.01,
                atr_14_pct=0.02,
                metadata_features={"blob": blob},
            )
        )
    return labels, features


def _write_sidecar_report(
    tmp_path: Path,
    *,
    results: list[RunResult],
    risk_auxiliary_by_run: dict[str, tuple[list[OutcomeLabelRecord], list[FeatureSnapshotRecord]]],
) -> Path:
    from app.backtests.artifacts import persist_backtest_report

    report = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="test",
        input_config={"runs": []},
        total_runs=len(results),
        successful_runs=len(results),
        failed_runs=0,
        status="success",
        results=results,
    )
    report_path = tmp_path / "report.json"
    persist_backtest_report(report, report_path, risk_auxiliary_by_run=risk_auxiliary_by_run)
    return report_path


def test_load_candidates_fails_when_empty(tmp_path: Path):
    report_path = tmp_path / "empty.json"
    _write_candidate_report(report_path, [])
    with pytest.raises(CandidateLoadError, match="No candidates found"):
        load_candidates_from_reports([report_path])


def test_build_risk_dataset_from_synthetic_report(tmp_path: Path):
    candidates = [
        CandidateRecord(
            candidate_id="abc123",
            strategy_id="breakout_channel",
            symbol="TEST",
            timestamp="2024-01-10T00:00:00+00:00",
            entry_price=102.0,
            planned_stop_pct=0.05,
            planned_target_pct=0.10,
            planned_horizon_bars=3,
            signal_score=0.87,
            signal_reason="breakout_channel|exits:a0b398e7ce",
            metadata={"rank": 3, "note": "ignored"},
            was_traded=False,
            reject_reason="session_window",
        )
    ]
    report_path = tmp_path / "report.json"
    _write_candidate_report(report_path, candidates)

    output_path = tmp_path / "risk_dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(min_history_bars=5, lookback_bars=5, include_index_features=False),
    )
    assert manifest.joined_rows == 1
    assert output_path.exists()

    df = pd.read_parquet(output_path)
    assert len(df) == 1
    assert df.iloc[0]["candidate_id"] == "abc123"
    assert "hit_stop_before_target" in df.columns
    assert "return_20" in df.columns
    assert "label_quality_flag" in df.columns
    selected, skipped = select_risk_feature_columns(df)
    assert "strategy_id" not in selected
    assert "signal_reason" not in selected
    assert "mae_pct" not in selected
    assert "hit_stop_before_target" not in selected
    assert "entry_price" in selected
    assert "return_20" in selected
    assert "meta_rank" in selected
    assert "meta_note" not in selected
    assert "meta_note" in skipped


def test_end_to_end_backtest_json_to_dataset(tmp_path: Path):
    raw = {
        "runs": [
            {
                "run_id": "csv_candidates",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {
                    "name": "breakout_channel",
                    "params": {
                        "lookback": 3,
                        "stake": 1.0,
                        "stop_loss_pct": 0.01,
                        "take_profit_pct": 0.02,
                        "max_hold_bars": 5,
                    },
                },
                "exit_rules": {
                    "rules": [
                        {"name": "channel_break", "params": {"lookback": 3}},
                        {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                        {"name": "max_hold_bars", "params": {"max_hold_bars": 5}},
                    ]
                },
                "analyzers": {"include_candidate_log": True},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)
    assert report.results[0].candidates

    report_path = tmp_path / "backtest.json"
    report_path.write_text(json.dumps(json.loads(report.model_dump_json())), encoding="utf-8")

    output_path = tmp_path / "dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(min_history_bars=5, lookback_bars=5, include_index_features=False),
    )
    assert manifest.joined_rows >= 1
    df = pd.read_parquet(output_path)
    assert not df.empty
    assert "label_quality_flag" in df.columns


def test_end_to_end_backtest_with_risk_auxiliary_sidecars(tmp_path: Path, monkeypatch):
    raw = {
        "runs": [
            {
                "run_id": "csv_candidates",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {
                    "name": "breakout_channel",
                    "params": {
                        "lookback": 3,
                        "stake": 1.0,
                        "stop_loss_pct": 0.01,
                        "take_profit_pct": 0.02,
                        "max_hold_bars": 5,
                    },
                },
                "exit_rules": {
                    "rules": [
                        {"name": "channel_break", "params": {"lookback": 3}},
                        {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                        {"name": "max_hold_bars", "params": {"max_hold_bars": 5}},
                    ]
                },
                "analyzers": {
                    "include_candidate_log": True,
                    "include_risk_auxiliary": True,
                },
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    from app.engine.runner import run_backtests_with_hooks
    from app.backtests.artifacts import persist_backtest_report

    execution = run_backtests_with_hooks(config, raw)
    assert execution.report.results[0].candidates
    assert execution.risk_auxiliary_by_run

    report_path = tmp_path / "job.json"
    written = persist_backtest_report(
        execution.report,
        report_path,
        risk_auxiliary_by_run=execution.risk_auxiliary_by_run,
    )
    assert written.labels_parquet_path is not None
    assert written.features_parquet_path is not None
    assert Path(written.labels_parquet_path).exists()
    assert Path(written.features_parquet_path).exists()

    def _forbidden_prepare(*args, **kwargs):
        raise AssertionError("BarStore.prepare should not run when sidecars exist")

    monkeypatch.setattr("app.risk.data.bars.BarStore.prepare", _forbidden_prepare)

    report_payload = json.loads(report_path.read_text(encoding="utf-8"))
    report_payload["results"][0]["symbol"] = "TEST"
    report_payload["results"][0]["candidates"] = []
    report_path.write_text(json.dumps(report_payload), encoding="utf-8")
    candidates_parquet_path = Path(written.candidates_parquet_path)
    if candidates_parquet_path.exists():
        candidates_parquet_path.unlink()

    output_path = tmp_path / "dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(min_history_bars=5, lookback_bars=5, include_index_features=False),
    )
    assert manifest.joined_rows >= 1
    df = pd.read_parquet(output_path)
    assert "run_id" in df.columns
    assert "symbol" in df.columns
    assert df["run_id"].iloc[0] == "csv_candidates"
    assert df["symbol"].iloc[0] == "TEST"
    assert isinstance(df["symbol"].dtype, pd.CategoricalDtype)
    assert "hit_stop_before_target" in df.columns
    assert "return_20" in df.columns


def test_build_risk_dataset_from_sidecars_without_candidates(tmp_path: Path):
    from app.backtests.artifacts import default_artifact_paths, persist_backtest_report

    # Create a report with no candidates, but write sidecar parquet files as if risk auxiliary was enabled.
    report = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="test",
        input_config={"runs": []},
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="csv_candidates",
                status="success",
                strategy="breakout_channel",
                symbol="TEST",
                data_source="csv",
                summary=RunSummary(
                    start_value=10_000.0,
                    end_value=10_100.0,
                    return_pct=1.0,
                    total_trades=0,
                    won_trades=0,
                    lost_trades=0,
                ),
                analyzers={"resolution": "1d"},
                candidates=[],
            )
        ],
    )

    report_path = tmp_path / "job.json"
    written = persist_backtest_report(report, report_path)
    paths = default_artifact_paths(tmp_path, report_path.stem)
    assert paths.labels_parquet_path is not None
    assert paths.features_parquet_path is not None

    labels_df = pd.DataFrame(
        [
            {
                "run_id": "csv_candidates",
                "candidate_id": "abc123",
                "label_version": "labels_v1",
                "entry_price": 100.0,
                "horizon_bars": 5,
                "stop_pct": 0.03,
                "target_pct": 0.06,
                "mae_pct": -0.01,
                "mae_abs_pct": 0.01,
                "mae_atr": None,
                "mfe_pct": 0.02,
                "final_return_pct": 0.01,
                "realized_R": 0.33,
                "hit_stop": False,
                "hit_target": False,
                "hit_stop_before_target": True,
                "bars_to_stop": None,
                "bars_to_target": None,
                "bars_held": 5,
                "exit_reason": "TIME",
                "label_quality_flag": "OK",
            }
        ]
    )
    features_df = pd.DataFrame(
        [
            {
                "run_id": "csv_candidates",
                "candidate_id": "abc123",
                "feature_version": "features_v1",
                "feature_timestamp": "2024-01-10T00:00:00+00:00",
                "feature_quality_flag": "OK",
                "return_20": 0.01,
                "atr_14_pct": 0.02,
            }
        ]
    )

    Path(paths.labels_parquet_path).parent.mkdir(parents=True, exist_ok=True)
    labels_df.to_parquet(paths.labels_parquet_path, index=False)
    features_df.to_parquet(paths.features_parquet_path, index=False)

    output_path = tmp_path / "dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(min_history_bars=5, lookback_bars=5, include_index_features=False),
    )
    assert manifest.joined_rows == 1
    df = pd.read_parquet(output_path)
    assert df.iloc[0]["candidate_id"] == "abc123"
    assert df.iloc[0]["timestamp"] == "2024-01-10T00:00:00+00:00"
    assert df.iloc[0]["run_id"] == "csv_candidates"
    assert df.iloc[0]["symbol"] == "TEST"
    assert isinstance(df["symbol"].dtype, pd.CategoricalDtype)
    assert "hit_stop_before_target" in df.columns
    assert "return_20" in df.columns


def test_risk_dataset_reader_loads_symbol_split_chunks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        RunResult(
            run_id="run-a",
            status="success",
            strategy="breakout_channel",
            symbol="AAPL",
            data_source="csv",
            summary=RunSummary(
                start_value=10_000.0,
                end_value=10_100.0,
                return_pct=1.0,
                total_trades=0,
                won_trades=0,
                lost_trades=0,
            ),
            analyzers={"resolution": "1d"},
            candidates=[],
        ),
        RunResult(
            run_id="run-b",
            status="success",
            strategy="breakout_channel",
            symbol="MSFT",
            data_source="csv",
            summary=RunSummary(
                start_value=10_000.0,
                end_value=10_100.0,
                return_pct=1.0,
                total_trades=0,
                won_trades=0,
                lost_trades=0,
            ),
            analyzers={"resolution": "1d"},
            candidates=[],
        ),
    ]
    risk_auxiliary_by_run = {
        "run-a": _make_split_sidecar_rows(run_id="run-a", row_count=12, blob_size=1800),
        "run-b": _make_split_sidecar_rows(run_id="run-b", row_count=12, blob_size=1800),
    }
    report_path = _write_sidecar_report(tmp_path, results=results, risk_auxiliary_by_run=risk_auxiliary_by_run)
    monkeypatch.setattr(
        "app.risk.dataset.builder._probe_parquet_size",
        lambda frame, temp_dir: len(frame) * 1_000,
    )

    output_path = tmp_path / "dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(
            min_history_bars=5,
            lookback_bars=5,
            include_index_features=False,
            max_parquet_file_size_bytes=15_000,
            parquet_split_primary_keys=["symbol"],
            parquet_split_fallback_keys=["run_id", "candidate_id"],
        ),
    )
    manifest_path = output_path.with_suffix(".manifest.json")
    reader = RiskDatasetReader.from_manifest_path(manifest_path)

    assert manifest.chunk_count == 2
    assert reader.chunk_count == 2
    assert [entry.split_key_values["symbol"] for entry in manifest.files] == ["AAPL", "MSFT"]
    assert all(Path(entry.path).exists() for entry in manifest.files)
    assert isinstance(manifest, RiskDatasetManifest)

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert RiskDatasetManifest.model_validate(payload)
    payload["unexpected"] = True
    with pytest.raises(ValidationError):
        RiskDatasetManifest.model_validate(payload)

    full_df = reader.load()
    assert len(full_df) == manifest.joined_rows
    assert set(full_df["symbol"].astype(str)) == {"AAPL", "MSFT"}
    aapl_df = reader.load_for_split(symbol="AAPL")
    assert len(aapl_df) == 12
    assert set(aapl_df["symbol"].astype(str)) == {"AAPL"}


def test_risk_dataset_reader_falls_back_to_run_split(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    results = [
        RunResult(
            run_id="run-a",
            status="success",
            strategy="breakout_channel",
            symbol="AAPL",
            data_source="csv",
            summary=RunSummary(
                start_value=10_000.0,
                end_value=10_100.0,
                return_pct=1.0,
                total_trades=0,
                won_trades=0,
                lost_trades=0,
            ),
            analyzers={"resolution": "1d"},
            candidates=[],
        ),
        RunResult(
            run_id="run-b",
            status="success",
            strategy="breakout_channel",
            symbol="AAPL",
            data_source="csv",
            summary=RunSummary(
                start_value=10_000.0,
                end_value=10_100.0,
                return_pct=1.0,
                total_trades=0,
                won_trades=0,
                lost_trades=0,
            ),
            analyzers={"resolution": "1d"},
            candidates=[],
        ),
    ]
    risk_auxiliary_by_run = {
        "run-a": _make_split_sidecar_rows(run_id="run-a", row_count=10, blob_size=1800),
        "run-b": _make_split_sidecar_rows(run_id="run-b", row_count=10, blob_size=1800),
    }
    report_path = _write_sidecar_report(tmp_path, results=results, risk_auxiliary_by_run=risk_auxiliary_by_run)
    monkeypatch.setattr(
        "app.risk.dataset.builder._probe_parquet_size",
        lambda frame, temp_dir: len(frame) * 1_000,
    )

    output_path = tmp_path / "dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(
            min_history_bars=5,
            lookback_bars=5,
            include_index_features=False,
            max_parquet_file_size_bytes=15_000,
            parquet_split_primary_keys=["symbol"],
            parquet_split_fallback_keys=["run_id"],
        ),
    )
    reader = RiskDatasetReader.from_manifest_path(output_path.with_suffix(".manifest.json"))

    assert manifest.chunk_count == 2
    assert {entry.split_key_values["run_id"] for entry in manifest.files} == {"run-a", "run-b"}
    assert all(entry.split_key_values["symbol"] == "AAPL" for entry in manifest.files)
    assert len(reader.load_for_split(symbol="AAPL")) == 20


def test_risk_dataset_reader_row_splits_when_single_value_is_too_large(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    results = [
        RunResult(
            run_id="run-a",
            status="success",
            strategy="breakout_channel",
            symbol="AAPL",
            data_source="csv",
            summary=RunSummary(
                start_value=10_000.0,
                end_value=10_100.0,
                return_pct=1.0,
                total_trades=0,
                won_trades=0,
                lost_trades=0,
            ),
            analyzers={"resolution": "1d"},
            candidates=[],
        )
    ]
    risk_auxiliary_by_run = {
        "run-a": _make_split_sidecar_rows(run_id="run-a", row_count=2, blob_size=10_000),
    }
    report_path = _write_sidecar_report(tmp_path, results=results, risk_auxiliary_by_run=risk_auxiliary_by_run)
    monkeypatch.setattr(
        "app.risk.dataset.builder._probe_parquet_size",
        lambda frame, temp_dir: 2_000 if len(frame) == 1 else 4_000,
    )

    output_path = tmp_path / "dataset.parquet"
    manifest = build_risk_dataset(
        [report_path],
        output_path=output_path,
        config=RiskDatasetConfig(
            min_history_bars=5,
            lookback_bars=5,
            include_index_features=False,
            max_parquet_file_size_bytes=1_000,
            parquet_split_primary_keys=["symbol"],
            parquet_split_fallback_keys=[],
        ),
    )
    reader = RiskDatasetReader.from_manifest_path(output_path.with_suffix(".manifest.json"))

    assert manifest.chunk_count == 2
    assert all(entry.split_key_values == {"symbol": "AAPL"} for entry in manifest.files)
    assert all(entry.size_bytes > manifest.max_parquet_file_size_bytes for entry in manifest.files)
    assert len(reader.load_for_split(symbol="AAPL")) == 2


def test_risk_build_dataset_argo_falls_back_to_reports_without_sidecars(tmp_path: Path, monkeypatch):
    from datetime import datetime, timezone

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.backtests.artifacts import persist_backtest_report
    from app.db.base import Base
    from app.db.models import BacktestJob
    from app.standalone.risk_build_dataset_argo import main as risk_build_dataset_main

    raw = {
        "runs": [
            {
                "run_id": "csv_candidates",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {
                    "name": "breakout_channel",
                    "params": {
                        "lookback": 3,
                        "stake": 1.0,
                        "stop_loss_pct": 0.01,
                        "take_profit_pct": 0.02,
                        "max_hold_bars": 5,
                    },
                },
                "exit_rules": {
                    "rules": [
                        {"name": "channel_break", "params": {"lookback": 3}},
                        {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                        {"name": "max_hold_bars", "params": {"max_hold_bars": 5}},
                    ]
                },
                "analyzers": {"include_candidate_log": True},
            }
        ]
    }
    config = BacktestConfig.model_validate(raw)
    report = run_backtests(config, raw)

    backtest_id = "4a594af71af249dba8d080b384694336"
    report_path = tmp_path / backtest_id / f"{backtest_id}.json"
    persist_backtest_report(report, report_path)
    assert not (tmp_path / backtest_id / f"{backtest_id}.labels.parquet").exists()
    assert not (tmp_path / backtest_id / f"{backtest_id}.features.parquet").exists()

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with test_session_factory() as session:
        session.add(
            BacktestJob(
                id=backtest_id,
                name="risk dataset source",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
                status="completed",
                report_status=report.status,
                total_runs=report.total_runs,
                completed_runs=report.total_runs,
                successful_runs=report.successful_runs,
                failed_runs=report.failed_runs,
                execution_backend="local",
                report_json_path=str(report_path),
            )
        )
        session.commit()

    monkeypatch.setattr("app.standalone.risk_build_dataset_argo.get_session_factory", lambda: test_session_factory)

    dataset_dir = tmp_path / "risk-models" / "group1"
    dataset_path_out = tmp_path / "dataset-path.txt"
    manifest_path_out = tmp_path / "manifest-path.txt"
    feature_cols_out = tmp_path / "feature-cols.json"
    terminal_command_out = tmp_path / "terminal-command.txt"

    risk_build_dataset_main(
        group_id="group1",
        backtest_ids_json=json.dumps([backtest_id]),
        dataset_config_json="{}",
        artifact_dir=str(dataset_dir),
        dataset_path_out=str(dataset_path_out),
        manifest_path_out=str(manifest_path_out),
        feature_cols_out=str(feature_cols_out),
        terminal_command_out=str(terminal_command_out),
    )

    dataset_path = Path(dataset_path_out.read_text(encoding="utf-8").strip())
    manifest_path = Path(manifest_path_out.read_text(encoding="utf-8").strip())
    feature_cols = json.loads(feature_cols_out.read_text(encoding="utf-8"))
    assert dataset_path.exists()
    assert manifest_path.exists()
    assert feature_cols
    df = pd.read_parquet(dataset_path)
    assert not df.empty
    assert "candidate_id" in df.columns


def test_risk_train_stop_accepts_canonical_stop_label_column(tmp_path: Path) -> None:
    from app.standalone.risk_train_stop_argo import main as risk_train_stop_main

    dataset_path = tmp_path / "dataset.parquet"
    pd.DataFrame(
        [
            {
                "candidate_id": "c1",
                "timestamp": "2024-01-01T00:00:00+00:00",
                "strategy_id": "breakout_channel|exits:a0b398e7ce",
                "hit_stop_before_target": 0,
                "feature_a": 1.0,
                "feature_b": 2.0,
                "signal_reason": "breakout",
                "mae_pct": 0.11,
            },
            {
                "candidate_id": "c2",
                "timestamp": "2024-01-02T00:00:00+00:00",
                "strategy_id": "breakout_channel|exits:a0b398e7ce",
                "hit_stop_before_target": 1,
                "feature_a": 2.0,
                "feature_b": 3.0,
                "signal_reason": "breakout",
                "mae_pct": 0.22,
            },
            {
                "candidate_id": "c3",
                "timestamp": "2024-01-03T00:00:00+00:00",
                "strategy_id": "breakout_channel|exits:a0b398e7ce",
                "hit_stop_before_target": 0,
                "feature_a": 3.0,
                "feature_b": 4.0,
                "signal_reason": "breakout",
                "mae_pct": 0.33,
            },
            {
                "candidate_id": "c4",
                "timestamp": "2024-01-04T00:00:00+00:00",
                "strategy_id": "breakout_channel|exits:a0b398e7ce",
                "hit_stop_before_target": 1,
                "feature_a": 4.0,
                "feature_b": 5.0,
                "signal_reason": "breakout",
                "mae_pct": 0.44,
            },
        ]
    ).to_parquet(dataset_path, index=False)

    artifact_dir = tmp_path / "artifacts"
    model_path_out = tmp_path / "model-path.txt"
    metrics_path_out = tmp_path / "metrics-path.txt"
    terminal_command_out = tmp_path / "terminal-command.txt"

    risk_train_stop_main(
        group_id="group1",
        dataset_path=str(dataset_path),
        manifest_path=str(tmp_path / "manifest.json"),
        feature_cols_json=json.dumps(["feature_a", "feature_b", "strategy_id", "signal_reason", "mae_pct"]),
        train_config_json=json.dumps(
            {
                "random_seed": 7,
                "calibration_test_size": 0.5,
                "walk_forward_train_days": 2,
                "walk_forward_test_days": 1,
                "walk_forward_step_days": 1,
                "walk_forward_embargo_bars": 0,
                "walk_forward_min_train_rows": 1,
                "walk_forward_min_validation_rows": 1,
                "walk_forward_min_test_rows": 1,
            }
        ),
        artifact_dir=str(artifact_dir),
        model_path_out=str(model_path_out),
        metrics_path_out=str(metrics_path_out),
        terminal_command_out=str(terminal_command_out),
    )

    model_path = Path(model_path_out.read_text(encoding="utf-8").strip())
    metrics_path = Path(metrics_path_out.read_text(encoding="utf-8").strip())
    assert model_path.exists()
    assert metrics_path.exists()
    serialized = json.loads(model_path.read_text(encoding="utf-8"))
    assert serialized["type"] in {"logreg+isotonic", "logreg+identity"}
    assert serialized["feature_cols"] == ["feature_a", "feature_b"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["walk_forward"]["n_folds"] >= 1
    assert metrics["aggregate"]["test"]["brier_calibrated_mean"] is not None
    assert metrics["fold_metrics"]


def test_risk_train_mae_accepts_canonical_mae_label_column(tmp_path: Path) -> None:
    from app.standalone.risk_train_mae_argo import main as risk_train_mae_main

    dataset_path = tmp_path / "dataset.parquet"
    pd.DataFrame(
        [
            {
                "candidate_id": "c1",
                "timestamp": "2024-01-01T00:00:00+00:00",
                "strategy_id": "breakout_channel|exits:a0b398e7ce",
                "mae_abs_pct": 0.11,
                "feature_a": 1.0,
                "feature_b": 2.0,
                "signal_reason": "breakout",
                "hit_stop_before_target": 0,
            },
            {
                "candidate_id": "c2",
                "timestamp": "2024-01-02T00:00:00+00:00",
                "strategy_id": "breakout_channel|exits:a0b398e7ce",
                "mae_abs_pct": 0.22,
                "feature_a": 2.0,
                "feature_b": 3.0,
                "signal_reason": "breakout",
                "hit_stop_before_target": 1,
            },
            {
                "candidate_id": "c3",
                "timestamp": "2024-01-03T00:00:00+00:00",
                "strategy_id": "breakout_channel|exits:a0b398e7ce",
                "mae_abs_pct": 0.33,
                "feature_a": 3.0,
                "feature_b": 4.0,
                "signal_reason": "breakout",
                "hit_stop_before_target": 0,
            },
            {
                "candidate_id": "c4",
                "timestamp": "2024-01-04T00:00:00+00:00",
                "strategy_id": "breakout_channel|exits:a0b398e7ce",
                "mae_abs_pct": 0.44,
                "feature_a": 4.0,
                "feature_b": 5.0,
                "signal_reason": "breakout",
                "hit_stop_before_target": 1,
            },
        ]
    ).to_parquet(dataset_path, index=False)

    artifact_dir = tmp_path / "artifacts"
    model_path_out = tmp_path / "model-path.txt"
    metrics_path_out = tmp_path / "metrics-path.txt"
    terminal_command_out = tmp_path / "terminal-command.txt"

    risk_train_mae_main(
        group_id="group1",
        dataset_path=str(dataset_path),
        manifest_path=str(tmp_path / "manifest.json"),
        feature_cols_json=json.dumps(["feature_a", "feature_b", "strategy_id", "signal_reason", "mae_abs_pct"]),
        train_config_json=json.dumps(
            {
                "random_seed": 7,
                "ridge_alpha": 1.0,
                "walk_forward_train_days": 2,
                "walk_forward_test_days": 1,
                "walk_forward_step_days": 1,
                "walk_forward_embargo_bars": 0,
                "walk_forward_min_train_rows": 1,
                "walk_forward_min_validation_rows": 1,
                "walk_forward_min_test_rows": 1,
            }
        ),
        artifact_dir=str(artifact_dir),
        model_path_out=str(model_path_out),
        metrics_path_out=str(metrics_path_out),
        terminal_command_out=str(terminal_command_out),
    )

    model_path = Path(model_path_out.read_text(encoding="utf-8").strip())
    metrics_path = Path(metrics_path_out.read_text(encoding="utf-8").strip())
    assert model_path.exists()
    assert metrics_path.exists()
    serialized = json.loads(model_path.read_text(encoding="utf-8"))
    assert serialized["type"] == "ridge"
    assert serialized["feature_cols"] == ["feature_a", "feature_b"]
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    assert metrics["walk_forward"]["n_folds"] >= 1
    assert metrics["aggregate"]["test"]["mae_mean"] is not None
    assert metrics["fold_metrics"]
