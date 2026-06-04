from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import app.standalone.risk_register_results_argo as mod


class _FakeRepo:
    captured_family: str | None = None
    status_updates: list[tuple[str, str, dict[str, object] | None]] = []
    target_updates: list[tuple[str, str, str]] = []

    def __init__(self, session_factory, *, family: str = "risk"):
        self.session_factory = session_factory
        type(self).captured_family = family

    def upsert_target(
        self,
        *,
        group_id: str,
        target_key: str,
        task_type: str,
        status: str,
        model_artifact_path: str | None,
        metrics: dict[str, object] | None,
        dataset_manifest_path: str | None,
        feature_columns: list[str] | None,
    ) -> None:
        type(self).target_updates.append((group_id, target_key, task_type))

    def update_group_status(
        self,
        group_id: str,
        *,
        status: str,
        summary_metrics: dict[str, object] | None = None,
    ) -> None:
        type(self).status_updates.append((group_id, status, summary_metrics))


def test_register_results_argo_uses_requested_family(tmp_path, monkeypatch) -> None:
    runner = CliRunner()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    stop_metrics_path = tmp_path / "stop-metrics.json"
    stop_metrics_path.write_text(json.dumps({"aggregate": {"validation": 1, "test": 2}}), encoding="utf-8")
    mae_metrics_path = tmp_path / "mae-metrics.json"
    mae_metrics_path.write_text(json.dumps({"aggregate": {"validation": 3, "test": 4}}), encoding="utf-8")

    monkeypatch.setattr(mod, "SqlAlchemyRiskModelRepository", _FakeRepo)
    monkeypatch.setattr(mod, "get_session_factory", lambda: object())
    _FakeRepo.captured_family = None
    _FakeRepo.status_updates = []
    _FakeRepo.target_updates = []

    result = runner.invoke(
        mod.app,
        [
            "--group-id",
            "return-1",
            "--family",
            "return_forecast",
            "--manifest-path",
            str(manifest_path),
            "--feature-cols-json",
            '["f1"]',
            "--stop-model-path",
            str(tmp_path / "stop.pkl"),
            "--stop-metrics-path",
            str(stop_metrics_path),
            "--mae-model-path",
            str(tmp_path / "mae.pkl"),
            "--mae-metrics-path",
            str(mae_metrics_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert _FakeRepo.captured_family == "return_forecast"
    assert _FakeRepo.target_updates == [("return-1", "stop_prob", "classification"), ("return-1", "mae", "regression")]
    assert _FakeRepo.status_updates and _FakeRepo.status_updates[0][0] == "return-1"
