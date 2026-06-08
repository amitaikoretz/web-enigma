from __future__ import annotations

import time
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Event

import yaml

from fastapi.testclient import TestClient

from app.datasets.models import DatasetListItem
from app.backtests.models import BacktestCreateRequest, BacktestDetailResponse, BacktestTradeReplayCapsule
from app.backtests.replay import build_trade_replay_capsule, build_trade_replay_launch_config
from app.backtests.service import BacktestArtifactStore, build_backtest_config, build_backtest_config_raw
from app.engine.runner import BacktestExecutionResult
from app.output.models import BacktestReport, CandidateRecord, OrderRecord, RunResult, RunSummary, TradeRecord
from tests.conftest import build_backtest_client


def _build_client(tmp_path) -> TestClient:
    return build_backtest_client(tmp_path)


def _wizard_payload() -> dict[str, object]:
    return {
        "start_date": "2024-01-01",
        "end_date": "2024-01-10",
        "resolution": "1d",
        "symbols": ["aapl", "msft"],
        "triggers": [
            {"name": "buy_and_hold", "params": {"stake": 1}},
            {"name": "sma_cross", "params": {"fast": 5, "slow": 10, "stake": 1}},
        ],
        "exit_rules": [
            {
                "rules": [
                    {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                    {"name": "max_hold_bars", "params": {"max_hold_bars": 24}},
                ]
            }
        ],
    }


def _wait_for_terminal_status(client: TestClient, backtest_id: str, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/backtests/{backtest_id}/status")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for backtest {backtest_id} to finish")


def _fake_runner(config, config_raw, on_run_complete=None, on_run_error=None, **_kwargs):
    results = []
    total = len(config.runs)
    for index, run in enumerate(config.runs, start=1):
        result = RunResult(
            run_id=run.run_id,
            name=run.name,
            status="success",
            strategy=(run.trigger.name if run.trigger else ""),
            symbol=run.data.symbol if hasattr(run.data, "symbol") else None,
            data_source=run.data.type,
            summary=RunSummary(
                start_value=10000.0,
                end_value=10500.0,
                return_pct=5.0,
                max_drawdown_pct=1.5,
                sharpe_ratio=1.2,
                total_trades=3,
                won_trades=2,
                lost_trades=1,
            ),
            orders=[
                OrderRecord(
                    datetime="2024-01-02T00:00:00+00:00",
                    status="Completed",
                    is_buy=True,
                    size=1.0,
                    price=100.0,
                    value=100.0,
                    commission=0.0,
                )
            ],
            trades=[
                TradeRecord(
                    entry_datetime="2024-01-02T00:00:00+00:00",
                    datetime="2024-01-03T00:00:00+00:00",
                    entry_bar_index=5,
                    exit_bar_index=8,
                    size=1.0,
                    price=105.0,
                    value=105.0,
                    pnl=5.0,
                    pnlcomm=5.0,
                )
            ],
        )
        if on_run_complete is not None:
            on_run_complete(result, index, total)
        results.append(result)

    return BacktestExecutionResult(
        report=BacktestReport(
            generated_at=datetime.now(timezone.utc),
            app_version="0.1.0",
            config_sha256="abc123",
            input_config=config_raw,
            total_runs=total,
            successful_runs=total,
            failed_runs=0,
            status="success",
            results=results,
        )
    )


def test_build_backtest_config_expands_symbols_and_triggers_cartesian() -> None:
    config = build_backtest_config(
        payload=BacktestCreateRequest.model_validate(
            {
                "start_date": "2024-01-01",
                "end_date": "2024-01-03",
                "resolution": "1d",
                "symbols": ["aapl", "msft"],
                "triggers": [
                    {"name": "buy_and_hold", "params": {"stake": 1}},
                    {"name": "sma_cross", "params": {"fast": 5, "slow": 10, "stake": 1}},
                ],
                "exit_rules": [
                    {
                        "rules": [
                            {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                            {"name": "max_hold_bars", "params": {"max_hold_bars": 24}},
                        ]
                    }
                ],
            }
        ),
        backtest_id="job123",
    )

    assert len(config.runs) == 4
    assert [run.data.symbol for run in config.runs] == ["AAPL", "MSFT", "AAPL", "MSFT"]
    assert [run.trigger.name for run in config.runs if run.trigger] == [
        "buy_and_hold",
        "buy_and_hold",
        "sma_cross",
        "sma_cross",
    ]


def test_build_backtest_config_includes_model_policy_per_run() -> None:
    payload = BacktestCreateRequest.model_validate(
        {
            "start_date": "2024-01-01",
            "end_date": "2024-01-03",
            "resolution": "1d",
            "symbols": ["aapl"],
            "triggers": [{"name": "buy_and_hold", "params": {"stake": 1}}],
            "exit_rules": [
                {
                    "rules": [
                        {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                    ]
                }
            ],
            "model_policy": {
                "forecast_model": {"group_id": "rf-1"},
                "risk_model": {"group_id": "rm-1"},
                "threshold_bps": 1.5,
                "target_edge_bps": 6.0,
                "max_risk_fraction": 0.002,
                "allow_short": False,
            },
        }
    )

    raw = build_backtest_config_raw(payload, "job123")
    assert raw["runs"][0]["model_policy"]["forecast_model"]["group_id"] == "rf-1"
    assert raw["runs"][0]["model_policy"]["risk_model"]["group_id"] == "rm-1"
    assert "models:" in raw["runs"][0]["run_id"]

    config = build_backtest_config(payload, backtest_id="job123")
    assert config.runs[0].model_policy is not None
    assert config.runs[0].model_policy.forecast_model is not None
    assert config.runs[0].model_policy.risk_model is not None


def test_build_backtest_config_uses_dataset_manifest_dates(tmp_path: Path) -> None:
    dataset_path = tmp_path / "dataset.parquet"
    manifest_path = tmp_path / "dataset.manifest.json"
    manifest_path.write_text(
        '{"symbol":"AAPL","provider":"alpaca","resolution":"1d","start_date":"2024-01-01","end_date":"2024-01-31","dataset_path":"'
        + str(dataset_path)
        + '"}',
        encoding="utf-8",
    )

    payload = BacktestCreateRequest.model_validate(
        {
            "dataset_path": str(dataset_path),
            "dataset_manifest_path": str(manifest_path),
            "resolution": "1d",
            "triggers": [{"name": "buy_and_hold", "params": {"stake": 1}}],
            "exit_rules": [
                {
                    "rules": [
                        {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                    ]
                }
            ],
        }
    )

    raw = build_backtest_config_raw(payload, "job123")
    run = raw["runs"][0]
    assert run["start_date"] == "2024-01-01"
    assert run["end_date"] == "2024-01-31"
    assert run["data"] == {"type": "parquet", "path": str(dataset_path)}


def test_create_backtest_can_resolve_dataset_paths_from_dataset_id(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    output_dir = tmp_path / "datasets"
    output_dir.mkdir()
    dataset_path = output_dir / "AAPL-alpaca-1d.parquet"
    manifest_path = output_dir / "AAPL-alpaca-1d.manifest.json"
    dataset_path.write_text("data", encoding="utf-8")
    manifest_path.write_text(
        '{"symbol":"AAPL","provider":"alpaca","resolution":"1d","start_date":"2024-01-01","end_date":"2024-01-31","dataset_path":"'
        + str(dataset_path)
        + '"}',
        encoding="utf-8",
    )

    client.app.state.deps.datasets.repository.create(
        DatasetListItem(
            id="ds-1",
            name="My dataset",
            symbol="AAPL",
            provider="alpaca",
            resolution="1d",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            created_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            status="completed",
            argo_namespace=None,
            argo_workflow_name=None,
            params_json={},
            output_dir=str(output_dir),
            dataset_parquet_path=None,
            manifest_path=None,
            options_parquet_path=None,
            options_manifest_path=None,
            error_message=None,
            progress_pct=100.0,
        )
    )

    response = client.post(
        "/backtests",
        json={
            "dataset_id": "ds-1",
            "resolution": "1d",
            "triggers": [{"name": "buy_and_hold", "params": {"stake": 1}}],
            "exit_rules": [
                {
                    "rules": [
                        {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                    ]
                }
            ],
        },
    )

    assert response.status_code == 202
    backtest_id = response.json()["backtest_id"]
    status_body = _wait_for_terminal_status(client, backtest_id)
    assert status_body["status"] == "completed"

    detail = client.get(f"/backtests/{backtest_id}").json()
    assert detail["report"]["input_config"]["runs"][0]["data"] == {"type": "parquet", "path": str(dataset_path)}


def test_create_backtest_argo_translates_dataset_path_to_workflow_mount(tmp_path: Path, monkeypatch) -> None:
    client = _build_client(tmp_path)

    workflow_root = tmp_path / "workflow-results"
    workflow_root.mkdir()
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", str(workflow_root))

    settings = client.app.state.deps.settings_service.load()
    settings.platform_behavior.backtest_execution_backend = "argo"
    client.app.state.deps.settings_service.save(settings)

    class _FakeArgoSubmitter:
        def __init__(self) -> None:
            self.last_submit: dict[str, str | None] | None = None

        @property
        def is_configured(self) -> bool:
            return True

        def submit(
            self,
            *,
            config_path: str,
            output_path: str,
            split_by: str,
            backtest_id: str,
            config_yaml: str | None = None,
        ) -> tuple[str, str]:
            self.last_submit = {
                "config_path": config_path,
                "output_path": output_path,
                "split_by": split_by,
                "backtest_id": backtest_id,
                "config_yaml": config_yaml,
            }
            return f"backtest-{backtest_id[:8]}", "backtest-workflows"

    fake_submitter = _FakeArgoSubmitter()
    client.app.state.deps.backtest_jobs.argo_submitter = fake_submitter

    output_dir = tmp_path / "datasets"
    output_dir.mkdir()
    dataset_path = output_dir / "AAPL-alpaca-1d.parquet"
    manifest_path = output_dir / "AAPL-alpaca-1d.manifest.json"
    dataset_path.write_text("data", encoding="utf-8")
    manifest_path.write_text(
        '{"symbol":"AAPL","provider":"alpaca","resolution":"1d","start_date":"2024-01-01","end_date":"2024-01-31","dataset_path":"'
        + str(dataset_path)
        + '"}',
        encoding="utf-8",
    )

    client.app.state.deps.datasets.repository.create(
        DatasetListItem(
            id="ds-1",
            name="My dataset",
            symbol="AAPL",
            provider="alpaca",
            resolution="1d",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            created_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 2, 1, tzinfo=timezone.utc),
            status="completed",
            argo_namespace=None,
            argo_workflow_name=None,
            params_json={},
            output_dir=str(output_dir),
            dataset_parquet_path=None,
            manifest_path=None,
            options_parquet_path=None,
            options_manifest_path=None,
            error_message=None,
            progress_pct=100.0,
        )
    )

    response = client.post(
        "/backtests",
        json={
            "dataset_id": "ds-1",
            "resolution": "1d",
            "triggers": [{"name": "buy_and_hold", "params": {"stake": 1}}],
            "exit_rules": [
                {
                    "rules": [
                        {"name": "fixed_pct_oco", "params": {"atr_period": 14, "sl_atr_mult": 1.5, "tp_atr_mult": 3.0}},
                    ]
                }
            ],
        },
    )

    assert response.status_code == 202
    assert fake_submitter.last_submit is not None
    config_yaml = fake_submitter.last_submit["config_yaml"]
    assert config_yaml is not None
    config_raw = yaml.safe_load(config_yaml)
    assert config_raw["runs"][0]["data"] == {
        "type": "parquet",
        "path": f"{workflow_root.resolve()}/AAPL-alpaca-1d.parquet",
    }
    assert fake_submitter.last_submit["output_path"] == f"{workflow_root.resolve()}/{response.json()['backtest_id']}/{response.json()['backtest_id']}.json"


def test_trade_replay_launch_config_exposes_alpaca_env_vars() -> None:
    capsule = BacktestTradeReplayCapsule.model_validate(
        {
            "backtest_id": "bt-1",
            "run_id": "run-1",
            "run_strategy": "demo",
            "trade_index": 0,
            "target_methods": ["app.strategies.implementations.PortableBacktestingStrategy.next"],
            "break_at": "entry",
            "trade": {
                "datetime": "2024-01-02T00:00:00+00:00",
                "size": 1.0,
                "price": 100.0,
                "value": 100.0,
                "pnl": 0.0,
                "pnlcomm": 0.0,
                "entry_datetime": "2024-01-01T00:00:00+00:00",
            },
            "trade_entry_time": "2024-01-01T00:00:00+00:00",
            "trade_exit_time": "2024-01-02T00:00:00+00:00",
            "config_text": "runs: []",
        }
    )

    launch_config = build_trade_replay_launch_config(capsule)

    assert launch_config["env"]["PYTHONPATH"] == "${workspaceFolder}/src"
    assert launch_config["env"]["ALPACA_API_KEY"] == "${env:ALPACA_API_KEY}"
    assert launch_config["env"]["ALPACA_SECRET_KEY"] == "${env:ALPACA_SECRET_KEY}"


def test_artifact_store_uses_path_agnostic_ids(tmp_path) -> None:
    store = BacktestArtifactStore(tmp_path)

    assert store.report_path("job123").name == "job123.json"
    assert store.config_path("job123").name == "job123.yaml"
    paths = store.artifact_paths("job123")
    assert "/job123/job123.candidates.parquet" in paths.candidates_parquet_path.replace("\\", "/")
    assert paths.orders_parquet_path.endswith("job123.orders.parquet")
    assert paths.trades_parquet_path.endswith("job123.trades.parquet")
    assert paths.rejections_parquet_path.endswith("job123.rejections.parquet")
    assert paths.labels_parquet_path.endswith("job123.labels.parquet")
    assert paths.features_parquet_path.endswith("job123.features.parquet")


def test_create_backtest_returns_202_and_persists_detail(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    payload = _wizard_payload()
    payload["name"] = "My named backtest"
    response = client.post("/backtests", json=payload)

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    assert body["status_url"].endswith(f"/backtests/{body['backtest_id']}/status")
    assert body["detail_url"].endswith(f"/backtests/{body['backtest_id']}")

    status_body = _wait_for_terminal_status(client, body["backtest_id"])
    assert status_body["status"] == "completed"
    assert status_body["is_terminal"] is True
    assert status_body["progress_pct"] == 100.0
    assert status_body["total_runs"] == 4
    assert status_body["successful_runs"] == 4

    detail = client.get(f"/backtests/{body['backtest_id']}")
    assert detail.status_code == 200
    detail_body = detail.json()
    assert detail_body["metadata"]["id"] == body["backtest_id"]
    assert detail_body["metadata"]["name"] == "My named backtest"
    assert detail_body["output_path"].endswith(f"/{body['backtest_id']}.json")
    assert detail_body["report"]["total_runs"] == 4
    assert detail_body["report"]["results"][0]["symbol"] == "AAPL"
    assert len(detail_body["report"]["results"][0]["orders"]) == 1
    assert len(detail_body["report"]["results"][0]["trades"]) == 1
    assert len(detail_body["artifacts"]) >= 3
    artifact_kinds = {entry["kind"] for entry in detail_body["artifacts"]}
    assert "report_json" in artifact_kinds
    assert "orders_parquet" in artifact_kinds
    assert "trades_parquet" in artifact_kinds


def test_patch_backtest_updates_name(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]

    updated = client.patch(f"/backtests/{backtest_id}", json={"name": "Renamed"})
    assert updated.status_code == 200
    assert updated.json()["id"] == backtest_id
    assert updated.json()["name"] == "Renamed"

    cleared = client.patch(f"/backtests/{backtest_id}", json={"name": "   "})
    assert cleared.status_code == 200
    assert cleared.json()["name"] is None

    detail = client.get(f"/backtests/{backtest_id}").json()
    assert detail["metadata"]["name"] is None


def test_list_backtests_includes_stored_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, backtest_id)

    listed = client.get("/backtests").json()["items"]
    item = next(entry for entry in listed if entry["id"] == backtest_id)
    kinds = {entry["kind"] for entry in item["stored_artifacts"]}
    assert "report_json" in kinds
    assert "orders_parquet" in kinds
    assert "trades_parquet" in kinds


def test_get_detail_hydrates_candidates_from_parquet(tmp_path, monkeypatch):
    def candidate_runner(config, config_raw, on_run_complete=None, on_run_error=None, **_kwargs):
        results = []
        total = len(config.runs)
        for index, run in enumerate(config.runs, start=1):
            result = RunResult(
                run_id=run.run_id,
                name=run.name,
                status="success",
                strategy=run.trigger.name if run.trigger else "",
                symbol=run.data.symbol if hasattr(run.data, "symbol") else None,
                data_source=run.data.type,
                summary=RunSummary(start_value=10000.0, end_value=10500.0, return_pct=5.0),
                analyzers={
                    "include_candidate_log": True,
                    "candidate_diagnostics": {
                        "total_candidates": 1,
                        "traded_candidates": 1,
                        "rejected_candidates": 0,
                    },
                },
                candidates=[
                    CandidateRecord(
                        candidate_id="cand-1",
                        strategy_id=run.trigger.name if run.trigger else "",
                        symbol=run.data.symbol if hasattr(run.data, "symbol") else "UNKNOWN",
                        timestamp="2024-01-02T00:00:00+00:00",
                        entry_price=100.0,
                        planned_stop_pct=0.02,
                        planned_horizon_bars=10,
                        was_traded=True,
                    )
                ],
            )
            if on_run_complete is not None:
                on_run_complete(result, index, total)
            results.append(result)

        return BacktestExecutionResult(
            report=BacktestReport(
                generated_at=datetime.now(timezone.utc),
                app_version="0.1.0",
                config_sha256="abc123",
                input_config=config_raw,
                total_runs=total,
                successful_runs=total,
                failed_runs=0,
                status="success",
                results=results,
            )
        )

    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", candidate_runner)
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests",
        json={
            "start_date": "2024-01-01",
            "end_date": "2024-01-10",
            "resolution": "1d",
            "symbols": ["aapl"],
            "triggers": [{"name": "buy_and_hold", "params": {"stake": 1}}],
            "exit_rules": [
                {
                    "rules": [
                        {"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}},
                    ]
                }
            ],
            "analyzers": {"include_candidate_log": True},
        },
    )
    assert response.status_code == 202
    backtest_id = response.json()["backtest_id"]
    _wait_for_terminal_status(client, backtest_id)

    detail = client.get(f"/backtests/{backtest_id}").json()
    result = detail["report"]["results"][0]
    assert result["analyzers"]["include_candidate_log"] is True
    assert result["analyzers"]["candidate_diagnostics"]["total_candidates"] == 1
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["candidate_id"] == "cand-1"


def test_build_trade_replay_capsule_targets_a_single_run(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, backtest_id)

    detail = BacktestDetailResponse.model_validate(client.get(f"/backtests/{backtest_id}").json())
    run = detail.report.results[0]
    capsule = build_trade_replay_capsule(detail, run_id=run.run_id, trade_index=0)
    launch_config = build_trade_replay_launch_config(capsule)

    assert capsule.backtest_id == backtest_id
    assert capsule.run_id == run.run_id
    assert capsule.trade_index == 0
    assert capsule.break_at == "entry"
    assert capsule.trade.entry_bar_index == 5
    assert capsule.target_methods == [
        "app.strategies.implementations.PortableBacktestingStrategy.next",
        "app.strategies.components.ComposableStrategyCore.on_bar",
    ]
    assert capsule.config_text.count("run_id:") == 1
    assert launch_config["module"] == "app.cli"
    assert launch_config["args"][0] == "replay-trade"
    assert launch_config["args"][1] == "--capsule-b64"


def test_create_backtest_uses_saved_settings_defaults_for_optional_fields(tmp_path, monkeypatch):
    captured = {}

    def fake_runner(config, config_raw, **kwargs):
        captured["config_raw"] = config_raw
        return _fake_runner(config, config_raw, **kwargs)

    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", fake_runner)
    client = _build_client(tmp_path)
    settings_payload = client.get("/settings").json()
    settings_payload["backtest_defaults"]["broker"]["cash"] = 25000
    settings_payload["backtest_defaults"]["execution"]["fill_model"] = "next_bar"
    settings_payload["backtest_defaults"]["analyzers"]["include_equity_curve"] = True
    put_response = client.put("/settings", json=settings_payload)
    assert put_response.status_code == 200

    response = client.post("/backtests", json=_wizard_payload())
    assert response.status_code == 202
    _wait_for_terminal_status(client, response.json()["backtest_id"])

    first_run = captured["config_raw"]["runs"][0]
    assert first_run["broker"]["cash"] == 25000
    assert first_run["execution"]["fill_model"] == "next_bar"
    assert first_run["analyzers"]["include_equity_curve"] is True


def test_backtest_status_reports_running_then_completed(tmp_path, monkeypatch):
    started = Event()
    finish = Event()

    def blocking_runner(config, config_raw, on_run_complete=None, on_run_error=None, **_kwargs):
        started.set()
        finish.wait(timeout=5)
        return _fake_runner(
            config,
            config_raw,
            on_run_complete=on_run_complete,
            on_run_error=on_run_error,
        )

    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", blocking_runner)
    client = _build_client(tmp_path)

    create = client.post("/backtests", json=_wizard_payload())
    backtest_id = create.json()["backtest_id"]

    assert started.wait(timeout=2)
    running = client.get(f"/backtests/{backtest_id}/status")
    assert running.status_code == 200
    running_body = running.json()
    assert running_body["status"] == "running"
    assert running_body["is_terminal"] is False
    assert running_body["progress_pct"] == 0.0

    finish.set()
    completed = _wait_for_terminal_status(client, backtest_id)
    assert completed["status"] == "completed"
    assert completed["is_terminal"] is True
    assert completed["progress_pct"] == 100.0


def test_retry_backtest_allows_force_clone_while_running(tmp_path, monkeypatch):
    started = Event()
    finish = Event()

    def blocking_runner(config, config_raw, on_run_complete=None, on_run_error=None, **_kwargs):
        started.set()
        finish.wait(timeout=5)
        return _fake_runner(
            config,
            config_raw,
            on_run_complete=on_run_complete,
            on_run_error=on_run_error,
        )

    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", blocking_runner)
    client = _build_client(tmp_path)

    create = client.post("/backtests", json=_wizard_payload())
    source_id = create.json()["backtest_id"]
    assert started.wait(timeout=2)

    blocked = client.post(f"/backtests/{source_id}/retry")
    assert blocked.status_code == 409

    forced = client.post(f"/backtests/{source_id}/retry", json={"force": True})
    assert forced.status_code == 202
    body = forced.json()
    assert body["source_backtest_id"] == source_id
    assert body["backtest_id"] != source_id

    finish.set()
    _wait_for_terminal_status(client, source_id)


def test_local_backtest_status_reports_incremental_progress(tmp_path, monkeypatch):
    progress_samples: list[float] = []

    def incremental_runner(config, config_raw, on_run_complete=None, on_run_error=None, **_kwargs):
        total = len(config.runs)
        for index, run in enumerate(config.runs, start=1):
            result = RunResult(
                run_id=run.run_id,
                name=run.name,
                status="success",
                strategy=run.trigger.name if run.trigger else "",
                symbol=run.data.symbol if hasattr(run.data, "symbol") else None,
                data_source=run.data.type,
                summary=RunSummary(
                    start_value=10000.0,
                    end_value=10500.0,
                    return_pct=5.0,
                    max_drawdown_pct=1.5,
                    sharpe_ratio=1.2,
                    total_trades=3,
                    won_trades=2,
                    lost_trades=1,
                ),
            )
            if on_run_complete is not None:
                on_run_complete(result, index, total)
            time.sleep(0.05)
        return _fake_runner(config, config_raw)

    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", incremental_runner)
    client = _build_client(tmp_path)

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]

    deadline = time.time() + 5.0
    while time.time() < deadline:
        body = client.get(f"/backtests/{backtest_id}/status").json()
        progress_samples.append(body["progress_pct"])
        if body["is_terminal"]:
            break
        time.sleep(0.02)

    assert max(progress_samples) == 100.0
    assert any(0 < value < 100 for value in progress_samples)


def test_argo_status_progress_from_shard_reports(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from app.backtests.models import BacktestListItem
    from app.backtests.sharding import ShardPlan, ShardSpec, write_shard_manifest

    class FakeArgoSubmitter:
        is_configured = True

        def get_workflow(self, workflow_name: str) -> dict | None:
            del workflow_name
            return {"status": {"phase": "Running", "progress": "0/1", "nodes": {}}}

        def get_workflow_phase(self, workflow_name: str) -> str | None:
            del workflow_name
            return "Running"

    client = _build_client(tmp_path)
    jobs = client.app.state.deps.backtest_jobs
    jobs.argo_submitter = FakeArgoSubmitter()
    repository = jobs.repository
    job_repository = jobs.job_repository
    backtest_id = "argo-progress-test"
    work_dir = repository.output_dir / backtest_id
    shards_dir = work_dir / "shards"
    shards_dir.mkdir(parents=True)
    shard_one = shards_dir / "aapl.json"
    shard_two = shards_dir / "msft.json"
    shard_one.write_text(
        BacktestReport(
            generated_at=datetime.now(UTC),
            app_version="0.1.0",
            config_sha256="abc",
            input_config={},
            total_runs=2,
            successful_runs=2,
            failed_runs=0,
            status="success",
            results=[],
        ).model_dump_json(),
        encoding="utf-8",
    )
    plan = ShardPlan(
        config_path=str(work_dir / "original.yaml"),
        split_by="symbol",
        shards=[
            ShardSpec(shard_id="aapl", config_path=str(shards_dir / "aapl.yaml"), output_path=str(shard_one)),
            ShardSpec(shard_id="msft", config_path=str(shards_dir / "msft.yaml"), output_path=str(shard_two)),
        ],
    )
    write_shard_manifest(plan, work_dir / "manifest.json")
    job_repository.create(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="running",
            total_runs=4,
            execution_backend="argo",
            workflow_name="backtest-argo-progress-test",
            workflow_namespace="backtest-workflows",
        ),
        paths=repository.artifact_paths(backtest_id),
    )

    body = client.get(f"/backtests/{backtest_id}/status").json()

    assert body["status"] == "running"
    assert body["completed_runs"] == 2
    assert body["progress_pct"] == 50.0
    assert body["is_terminal"] is False


def test_list_backtests_uses_argo_workflow_progress_pct(tmp_path):
    from datetime import UTC, datetime

    from app.backtests.models import BacktestListItem

    class FakeArgoSubmitter:
        is_configured = True

        def get_workflow(self, workflow_name: str) -> dict | None:
            del workflow_name
            return {"status": {"phase": "Running", "progress": "37/100"}}

    client = _build_client(tmp_path)
    jobs = client.app.state.deps.backtest_jobs
    jobs.argo_submitter = FakeArgoSubmitter()

    repository = jobs.repository
    job_repository = jobs.job_repository
    backtest_id = "argo-list-progress-test"

    job_repository.create(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="running",
            total_runs=400,
            completed_runs=0,
            execution_backend="argo",
            workflow_name="backtest-argo-list-progress-test",
            workflow_namespace="backtest-workflows",
        ),
        paths=repository.artifact_paths(backtest_id),
    )

    listed = client.get("/backtests").json()["items"]
    item = next(entry for entry in listed if entry["id"] == backtest_id)
    assert item["progress_pct"] == 37.0
    assert item["progress_source"] == "argo"
    assert item["completed_runs"] == 0


def test_argo_status_reconciles_to_completed_on_read(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from app.backtests.models import BacktestListItem
    from app.backtests.persistence import BacktestArtifactPaths

    class FakeArgoSubmitter:
        is_configured = True

        def get_workflow(self, workflow_name: str) -> dict | None:
            del workflow_name
            return {"status": {"phase": "Succeeded", "progress": "1/1", "nodes": {}}}

        def get_workflow_phase(self, workflow_name: str) -> str | None:
            del workflow_name
            return "Succeeded"

    client = _build_client(tmp_path)
    jobs = client.app.state.deps.backtest_jobs
    jobs.argo_submitter = FakeArgoSubmitter()
    repository = jobs.repository
    job_repository = jobs.job_repository
    backtest_id = "argo-reconcile-test"
    job_repository.create(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="running",
            total_runs=1,
            execution_backend="argo",
            workflow_name="backtest-argo-reconcile-test",
            workflow_namespace="backtest-workflows",
        ),
        paths=repository.artifact_paths(backtest_id),
    )
    repository.save_report(
        backtest_id,
        BacktestReport(
            generated_at=datetime.now(UTC),
            app_version="0.1.0",
            config_sha256="abc",
            input_config={},
            total_runs=1,
            successful_runs=1,
            failed_runs=0,
            status="success",
            results=[],
        ),
    )
    job_repository.update_paths(
        backtest_id,
        BacktestArtifactPaths(report_json_path=str(repository.report_path(backtest_id).resolve())),
    )

    body = client.get(f"/backtests/{backtest_id}/status").json()

    assert body["status"] == "completed"
    assert body["is_terminal"] is True
    assert body["progress_pct"] == 100.0


def test_run_job_writes_db_paths(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)
    jobs = client.app.state.deps.backtest_jobs

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, backtest_id)

    paths = jobs.job_repository.get_paths(backtest_id)
    assert paths is not None
    assert paths.report_json_path is not None
    assert Path(paths.report_json_path).is_file()


def test_reconciler_completes_when_db_path_outside_output_dir(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from app.backtests.models import BacktestListItem
    from app.backtests.persistence import BacktestArtifactPaths

    class FakeArgoSubmitter:
        is_configured = True

        def get_workflow(self, workflow_name: str) -> dict | None:
            del workflow_name
            return {"status": {"phase": "Succeeded", "progress": "1/1", "nodes": {}}}

        def get_workflow_phase(self, workflow_name: str) -> str | None:
            del workflow_name
            return "Succeeded"

    client = _build_client(tmp_path)
    jobs = client.app.state.deps.backtest_jobs
    jobs.argo_submitter = FakeArgoSubmitter()
    job_repository = jobs.job_repository
    backtest_id = "argo-external-path-test"
    external_dir = tmp_path / "workflow-results"
    external_dir.mkdir()
    report_path = external_dir / f"{backtest_id}.json"
    report_path.write_text(
        BacktestReport(
            generated_at=datetime.now(UTC),
            app_version="0.1.0",
            config_sha256="abc",
            input_config={},
            total_runs=1,
            successful_runs=1,
            failed_runs=0,
            status="success",
            results=[],
        ).model_dump_json(),
        encoding="utf-8",
    )
    job_repository.create(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="running",
            total_runs=1,
            execution_backend="argo",
            workflow_name="backtest-external-path-test",
            workflow_namespace="backtest-workflows",
        ),
        paths=BacktestArtifactPaths(report_json_path=str(report_path.resolve())),
    )

    body = client.get(f"/backtests/{backtest_id}/status").json()

    assert body["status"] == "completed"
    assert body["is_terminal"] is True


def test_merge_updates_db_paths_without_http(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.backtests.models import BacktestListItem
    from app.backtests.persistence import SqlAlchemyBacktestJobRepository
    from app.backtests.sharding import plan_shards, write_shard_manifest
    from app.cli import _cmd_merge
    from app.db.base import Base
    from app.output.models import BacktestReport, RunResult, RunSummary
    from tests.test_backtest_sharding import _sample_config_raw

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    monkeypatch.setattr("app.backtests.argo_reconciler.get_session_factory", lambda: test_session_factory)

    job_repository = SqlAlchemyBacktestJobRepository(test_session_factory)
    backtest_id = "merge-db-path-test"
    job_repository.create(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="running",
            total_runs=1,
            execution_backend="argo",
            workflow_name="backtest-merge-db-path-test",
            workflow_namespace="backtest-workflows",
        ),
    )

    raw = _sample_config_raw()
    work_dir = tmp_path / "work"
    plan = plan_shards(raw, split_by="run", work_dir=work_dir)
    for shard in plan.shards:
        report = BacktestReport(
            generated_at=datetime.now(UTC),
            app_version="test",
            config_sha256="abc",
            input_config=raw,
            total_runs=1,
            successful_runs=1,
            failed_runs=0,
            status="success",
            results=[
                RunResult(
                    run_id=shard.shard_id,
                    status="success",
                    strategy="sma_cross",
                    symbol="AAPL",
                    data_source="csv",
                    summary=RunSummary(start_value=10000, end_value=10050, return_pct=0.5),
                )
            ],
        )
        Path(shard.output_path).write_text(report.model_dump_json(), encoding="utf-8")
    manifest_path = work_dir / "manifest.json"
    write_shard_manifest(plan, manifest_path)
    output_path = tmp_path / "shared-results" / f"{backtest_id}.json"
    output_path.parent.mkdir(parents=True)

    exit_code = _cmd_merge(str(manifest_path), str(output_path), backtest_id)

    assert exit_code == 0
    assert output_path.is_file()
    paths = job_repository.get_paths(backtest_id)
    assert paths is not None
    assert paths.report_json_path == str(output_path.resolve())
    metadata = job_repository.get(backtest_id)
    assert metadata is not None
    assert metadata.status == "completed"
    assert metadata.report_status == "success"


def test_list_backtests_returns_newest_first(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    first = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, first)
    time.sleep(0.02)
    second = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, second)

    response = client.get("/backtests")

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body["items"]]
    assert body["total"] == 2
    assert body["page"] == 1
    assert body["page_size"] == 25
    assert ids[:2] == [second, first]


def test_list_backtests_supports_pagination(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    created_ids: list[str] = []
    for _ in range(3):
        backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
        _wait_for_terminal_status(client, backtest_id)
        created_ids.append(backtest_id)
        time.sleep(0.02)

    page_one = client.get("/backtests", params={"page": 1, "page_size": 2})
    page_two = client.get("/backtests", params={"page": 2, "page_size": 2})
    beyond = client.get("/backtests", params={"page": 99, "page_size": 2})
    invalid = client.get("/backtests", params={"page": 0, "page_size": 2})

    assert page_one.status_code == 200
    page_one_body = page_one.json()
    assert page_one_body["total"] == 3
    assert page_one_body["page"] == 1
    assert page_one_body["page_size"] == 2
    assert len(page_one_body["items"]) == 2
    assert [item["id"] for item in page_one_body["items"]] == created_ids[-1:-3:-1]

    assert page_two.status_code == 200
    page_two_body = page_two.json()
    assert page_two_body["page"] == 2
    assert len(page_two_body["items"]) == 1
    assert page_two_body["items"][0]["id"] == created_ids[0]

    assert beyond.status_code == 200
    assert beyond.json()["items"] == []

    assert invalid.status_code == 422


def test_completed_backtest_records_wall_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    body = _wait_for_terminal_status(client, backtest_id)

    assert body["started_at"] is not None
    assert body["finished_at"] is not None
    assert body["status"] == "completed"

    list_item = client.get("/backtests", params={"page": 1, "page_size": 1}).json()["items"][0]
    assert list_item["started_at"] is not None
    assert list_item["finished_at"] is not None


def test_create_backtest_rejects_invalid_dates_and_empty_selections(tmp_path):
    client = _build_client(tmp_path)

    empty_response = client.post(
        "/backtests",
        json={
            "start_date": "2024-01-10",
            "end_date": "2024-01-12",
            "resolution": "1d",
            "symbols": [],
            "triggers": [],
            "exit_rules": [],
        },
    )
    invalid_dates_response = client.post(
        "/backtests",
        json={
            "start_date": "2024-01-10",
            "end_date": "2024-01-01",
            "resolution": "1d",
            "symbols": ["AAPL"],
            "triggers": [{"name": "buy_and_hold", "params": {"stake": 1}}],
            "exit_rules": [
                {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            ],
        },
    )

    assert empty_response.status_code == 422
    assert "at least 1 item" in empty_response.text
    assert invalid_dates_response.status_code == 422
    assert "start_date must be <=" in invalid_dates_response.text


def test_create_backtest_rejects_invalid_strategy_overrides(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests",
        json={
            "start_date": "2024-01-01",
            "end_date": "2024-01-10",
            "resolution": "1d",
            "symbols": ["AAPL"],
            "triggers": [{"name": "sma_cross", "params": {"fast": 20, "slow": 10, "stake": 1}}],
            "exit_rules": [
                {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            ],
        },
    )

    assert response.status_code == 422
    assert "Invalid params for trigger 'sma_cross'" in response.text


def test_get_backtest_and_status_return_404_for_unknown_id(tmp_path):
    client = _build_client(tmp_path)

    detail = client.get("/backtests/missing-job")
    status_response = client.get("/backtests/missing-job/status")

    assert detail.status_code == 404
    assert status_response.status_code == 404


def test_list_backtests_returns_api_error_detail_on_unhandled_failure(tmp_path, monkeypatch):
    client = _build_client(tmp_path)

    def fail_count() -> int:
        raise RuntimeError("relation backtest_jobs does not exist")

    monkeypatch.setattr(
        client.app.state.deps.backtest_jobs.job_repository,
        "count",
        fail_count,
    )

    response = TestClient(client.app, raise_server_exceptions=False).get("/backtests")

    assert response.status_code == 500
    assert response.json()["detail"] == "relation backtest_jobs does not exist"


def test_get_backtest_report_returns_json_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, backtest_id)

    response = client.get(f"/backtests/{backtest_id}/report")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.headers["content-disposition"].endswith(f'filename="{backtest_id}.json"')
    assert response.json()["total_runs"] == 4


def test_get_backtest_report_returns_404_when_missing(tmp_path):
    client = _build_client(tmp_path)

    response = client.get("/backtests/missing-job/report")

    assert response.status_code == 404


def test_get_backtest_config_returns_yaml_file(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, backtest_id)

    response = client.get(f"/backtests/{backtest_id}/config")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-yaml")
    assert response.headers["content-disposition"].endswith(f'filename="{backtest_id}.yaml"')
    assert "runs:" in response.text
    assert "buy_and_hold" in response.text


def test_get_backtest_config_returns_404_when_missing(tmp_path):
    client = _build_client(tmp_path)

    response = client.get("/backtests/missing-job/config")

    assert response.status_code == 404


def test_delete_backtest_removes_db_row_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)
    jobs = client.app.state.deps.backtest_jobs
    repository = jobs.repository
    job_repository = jobs.job_repository

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, backtest_id)

    assert repository.report_path(backtest_id).exists()
    assert job_repository.get(backtest_id) is not None
    assert repository.config_path(backtest_id).exists()

    response = client.delete(f"/backtests/{backtest_id}")

    assert response.status_code == 204
    assert not repository.report_path(backtest_id).exists()
    assert job_repository.get(backtest_id) is None
    assert not repository.config_path(backtest_id).exists()
    assert client.get(f"/backtests/{backtest_id}").status_code == 404


def test_delete_backtest_returns_404_for_unknown_id(tmp_path):
    client = _build_client(tmp_path)

    response = client.delete("/backtests/missing-job")

    assert response.status_code == 404


def test_build_backtest_config_risk_auxiliary_enables_candidate_log() -> None:
    config = build_backtest_config(
        payload=BacktestCreateRequest.model_validate(
            {
                "start_date": "2024-01-01",
                "end_date": "2024-01-03",
                "resolution": "1d",
                "symbols": ["AAPL"],
                "triggers": [{"name": "buy_and_hold", "params": {"stake": 1}}],
                "exit_rules": [{"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]}],
                "analyzers": {
                    "include_equity_curve": False,
                    "include_trade_log": True,
                    "include_order_log": True,
                    "include_candidate_log": False,
                    "include_risk_auxiliary": True,
                },
            }
        ),
        backtest_id="job123",
    )

    assert config.runs[0].analyzers.include_risk_auxiliary is True
    assert config.runs[0].analyzers.include_candidate_log is True


def _write_backtest_config(tmp_path: Path, backtest_id: str, config_raw: dict[str, object]) -> Path:
    config_path = tmp_path / "api-results" / backtest_id / f"{backtest_id}.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(yaml.safe_dump(config_raw), encoding="utf-8")
    return config_path


def _sample_retry_config(source_id: str) -> dict[str, object]:
    return {
        "runs": [
            {
                "run_id": f"{source_id}:001:AAPL:buy_and_hold",
                "start_date": "2024-01-01",
                "end_date": "2024-01-10",
                "data": {
                    "type": "alpaca",
                    "symbol": "AAPL",
                    "interval": "1d",
                    "feed": "iex",
                },
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }


def test_rewrite_run_ids_replaces_backtest_prefix() -> None:
    from app.backtests.service import _rewrite_run_ids

    source_id = "source123"
    rewritten = _rewrite_run_ids(_sample_retry_config(source_id), "new456")

    assert rewritten["runs"][0]["run_id"] == "new456:001:AAPL:buy_and_hold"


def test_retry_backtest_creates_new_job_from_saved_config(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)
    source_id = "failed123"
    _write_backtest_config(tmp_path, source_id, _sample_retry_config(source_id))

    response = client.post(f"/backtests/{source_id}/retry")

    assert response.status_code == 202
    body = response.json()
    new_id = body["backtest_id"]
    assert new_id != source_id
    assert body["source_backtest_id"] == source_id

    new_config = yaml.safe_load((tmp_path / "api-results" / new_id / f"{new_id}.yaml").read_text(encoding="utf-8"))
    assert new_config["runs"][0]["run_id"] == f"{new_id}:001:AAPL:buy_and_hold"

    status_body = _wait_for_terminal_status(client, new_id)
    assert status_body["status"] == "completed"


def test_retry_backtest_rejects_missing_config(tmp_path) -> None:
    client = _build_client(tmp_path)

    response = client.post("/backtests/missing-id/retry")

    assert response.status_code == 404


def test_retry_backtest_rejects_active_source_job(tmp_path, monkeypatch) -> None:
    started = Event()

    def slow_runner(*_args, **_kwargs):
        started.set()
        started.wait(timeout=5.0)
        return _fake_runner(*_args, **_kwargs)

    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", slow_runner)
    client = _build_client(tmp_path)

    create_response = client.post("/backtests", json=_wizard_payload())
    source_id = create_response.json()["backtest_id"]
    assert started.wait(timeout=5.0)

    response = client.post(f"/backtests/{source_id}/retry")

    assert response.status_code == 409
    started.set()
