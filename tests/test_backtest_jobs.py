from __future__ import annotations

import time
from datetime import datetime, timezone
from threading import Event

from fastapi.testclient import TestClient

from app.api import create_app
from app.backtests.models import BacktestCreateRequest
from app.backtests.service import BacktestResultRepository, build_backtest_config
from app.config.models import DataCacheConfig
from app.output.models import BacktestReport, RunResult, RunSummary


def _build_client(tmp_path) -> TestClient:
    return TestClient(
        create_app(
            cache_config=DataCacheConfig(directory=str(tmp_path / "cache")),
            output_dir=tmp_path / "api-results",
            log_file=tmp_path / "api.log",
        )
    )


def _wizard_payload() -> dict[str, object]:
    return {
        "start_date": "2024-01-01",
        "end_date": "2024-01-10",
        "resolution": "1d",
        "symbols": ["aapl", "msft"],
        "strategies": [
            {"name": "buy_and_hold", "params": {"stake": 1}},
            {"name": "sma_cross", "params": {"fast": 5, "slow": 10}},
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
            strategy=run.strategy or "",
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
        results.append(result)

    return BacktestReport(
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


def test_build_backtest_config_expands_symbols_and_strategies_cartesian() -> None:
    config = build_backtest_config(
        payload=BacktestCreateRequest.model_validate(
            {
                "start_date": "2024-01-01",
                "end_date": "2024-01-03",
                "resolution": "1d",
                "symbols": ["aapl", "msft"],
                "strategies": [
                    {"name": "buy_and_hold", "params": {"stake": 1}},
                    {"name": "sma_cross", "params": {"fast": 5, "slow": 10}},
                ],
            }
        ),
        backtest_id="job123",
    )

    assert len(config.runs) == 4
    assert [run.data.symbol for run in config.runs] == ["AAPL", "MSFT", "AAPL", "MSFT"]
    assert [run.strategy for run in config.runs] == [
        "buy_and_hold",
        "buy_and_hold",
        "sma_cross",
        "sma_cross",
    ]


def test_result_repository_uses_path_agnostic_ids(tmp_path) -> None:
    repository = BacktestResultRepository(tmp_path)

    assert repository.report_path("job123").name == "job123.json"
    assert repository.metadata_path("job123").name == "job123.meta.json"
    assert repository.config_path("job123").name == "job123.yaml"


def test_create_backtest_returns_202_and_persists_detail(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)

    response = client.post("/backtests", json=_wizard_payload())

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
    assert detail_body["output_path"].endswith(f"/{body['backtest_id']}.json")
    assert detail_body["report"]["total_runs"] == 4
    assert detail_body["report"]["results"][0]["symbol"] == "AAPL"


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


def test_local_backtest_status_reports_incremental_progress(tmp_path, monkeypatch):
    progress_samples: list[float] = []

    def incremental_runner(config, config_raw, on_run_complete=None, on_run_error=None, **_kwargs):
        total = len(config.runs)
        for index, run in enumerate(config.runs, start=1):
            result = RunResult(
                run_id=run.run_id,
                name=run.name,
                status="success",
                strategy=run.strategy or "",
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

        def get_workflow_phase(self, workflow_name: str) -> str | None:
            del workflow_name
            return "Running"

    client = _build_client(tmp_path)
    client.app.state.deps.backtest_jobs.argo_submitter = FakeArgoSubmitter()
    repository = BacktestResultRepository(tmp_path / "api-results")
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
    repository.write_metadata(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="running",
            total_runs=4,
            execution_backend="argo",
            workflow_name="backtest-argo-progress-test",
            workflow_namespace="backtest-workflows",
        )
    )

    body = client.get(f"/backtests/{backtest_id}/status").json()

    assert body["status"] == "running"
    assert body["completed_runs"] == 2
    assert body["progress_pct"] == 50.0
    assert body["is_terminal"] is False


def test_argo_status_reconciles_to_completed_on_read(tmp_path, monkeypatch):
    from datetime import UTC, datetime

    from app.backtests.models import BacktestListItem

    class FakeArgoSubmitter:
        is_configured = True

        def get_workflow_phase(self, workflow_name: str) -> str | None:
            del workflow_name
            return "Succeeded"

    client = _build_client(tmp_path)
    client.app.state.deps.backtest_jobs.argo_submitter = FakeArgoSubmitter()
    repository = BacktestResultRepository(tmp_path / "api-results")
    backtest_id = "argo-reconcile-test"
    repository.write_metadata(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="running",
            total_runs=1,
            execution_backend="argo",
            workflow_name="backtest-argo-reconcile-test",
            workflow_namespace="backtest-workflows",
        )
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

    body = client.get(f"/backtests/{backtest_id}/status").json()

    assert body["status"] == "completed"
    assert body["is_terminal"] is True
    assert body["progress_pct"] == 100.0


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
    ids = [item["id"] for item in response.json()]
    assert ids[:2] == [second, first]


def test_create_backtest_rejects_invalid_dates_and_empty_selections(tmp_path):
    client = _build_client(tmp_path)

    empty_response = client.post(
        "/backtests",
        json={
            "start_date": "2024-01-10",
            "end_date": "2024-01-12",
            "resolution": "1d",
            "symbols": [],
            "strategies": [],
        },
    )
    invalid_dates_response = client.post(
        "/backtests",
        json={
            "start_date": "2024-01-10",
            "end_date": "2024-01-01",
            "resolution": "1d",
            "symbols": ["AAPL"],
            "strategies": [{"name": "buy_and_hold", "params": {"stake": 1}}],
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
            "strategies": [{"name": "sma_cross", "params": {"fast": 20, "slow": 10}}],
        },
    )

    assert response.status_code == 422
    assert "Invalid params for strategy 'sma_cross'" in response.text


def test_get_backtest_and_status_return_404_for_unknown_id(tmp_path):
    client = _build_client(tmp_path)

    detail = client.get("/backtests/missing-job")
    status_response = client.get("/backtests/missing-job/status")

    assert detail.status_code == 404
    assert status_response.status_code == 404


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


def test_delete_backtest_removes_metadata_and_report(tmp_path, monkeypatch):
    monkeypatch.setattr("app.backtests.service.run_backtests_with_hooks", _fake_runner)
    client = _build_client(tmp_path)
    repository = BacktestResultRepository(tmp_path / "api-results")

    backtest_id = client.post("/backtests", json=_wizard_payload()).json()["backtest_id"]
    _wait_for_terminal_status(client, backtest_id)

    assert repository.report_path(backtest_id).exists()
    assert repository.metadata_path(backtest_id).exists()
    assert repository.config_path(backtest_id).exists()

    response = client.delete(f"/backtests/{backtest_id}")

    assert response.status_code == 204
    assert not repository.report_path(backtest_id).exists()
    assert not repository.metadata_path(backtest_id).exists()
    assert not repository.config_path(backtest_id).exists()
    assert client.get(f"/backtests/{backtest_id}").status_code == 404


def test_delete_backtest_returns_404_for_unknown_id(tmp_path):
    client = _build_client(tmp_path)

    response = client.delete("/backtests/missing-job")

    assert response.status_code == 404
