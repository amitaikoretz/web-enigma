from __future__ import annotations

import json
from pathlib import Path

import yaml

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from datetime import UTC, datetime, timedelta

from app.api import create_app
from app.api.live_runtime_deps import LiveRuntimeStores, get_live_runtime_stores
from app.api_logging import build_timestamped_log_file
from app.config.models import DataCacheConfig
from app.db.base import Base
from app.db.models import WorkerEvent
from app.db.session import get_db_session
from app.live.assignments import RedisAssignmentStore, get_shared_redis_backend, heartbeat_from_runtime
from app.live.control_flags import RedisControlFlagStore
from app.live.leases import RedisLeaseStore
from app.live.models import LeaseAcquireRequest, RuntimeContractState
from app.output.models import BacktestReport, RunResult, RunSummary, TradeRecord
from app.backtests.models import BacktestListItem
from app.backtests.persistence import BacktestArtifactPaths


def _mock_alpaca_payload() -> bytes:
    payload = {
        "bars": [
            {"t": "2024-01-01T00:00:00Z", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 1000},
            {"t": "2024-01-02T00:00:00Z", "o": 101.0, "h": 102.0, "l": 100.0, "c": 101.5, "v": 1100},
        ],
        "next_page_token": None,
    }
    return json.dumps(payload).encode("utf-8")


class _FakeResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        return False


def _build_client(tmp_path) -> TestClient:
    from tests.conftest import build_backtest_client

    return build_backtest_client(tmp_path)


def _build_contract_client(tmp_path) -> tuple[TestClient, sessionmaker[Session]]:
    app = create_app(
        DataCacheConfig(directory=str(tmp_path)),
        output_dir=tmp_path / "api-results",
        log_file=tmp_path / "api.log",
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_db_session():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_db_session
    return TestClient(app), test_session_factory


def _build_live_runtime_client(tmp_path) -> tuple[TestClient, sessionmaker[Session], LiveRuntimeStores]:
    app = create_app(
        DataCacheConfig(directory=str(tmp_path)),
        output_dir=tmp_path / "api-results",
        log_file=tmp_path / "api.log",
    )
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override_db_session():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    redis_url = f"memory://live-runtime-api-{id(tmp_path)}"
    backend = get_shared_redis_backend(redis_url)
    stores = LiveRuntimeStores(
        assignment_store=RedisAssignmentStore(backend=backend, key_prefix="ta"),
        lease_store=RedisLeaseStore(backend=backend, key_prefix="ta"),
        control_flag_store=RedisControlFlagStore(backend=backend, key_prefix="ta"),
    )

    app.dependency_overrides[get_db_session] = override_db_session
    app.dependency_overrides[get_live_runtime_stores] = lambda: stores
    return TestClient(app), test_session_factory, stores


def _csv_backtest_payload() -> dict[str, object]:
    return {
        "runs": [
            {
                "run_id": "api_run",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
            }
        ]
    }


def _read_report(output_path: str) -> tuple[dict[str, object], BacktestReport]:
    path = Path(output_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    report = BacktestReport.model_validate(raw)
    return raw, report


def test_health(tmp_path):
    client = TestClient(create_app(log_file=tmp_path / "api.log"))
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_build_timestamped_log_file_uses_local_timestamp():
    log_file = build_timestamped_log_file(Path("logs"), now=datetime(2026, 5, 24, 14, 30, 52))

    assert log_file == Path("logs/api-20260524T143052.log")


def test_api_writes_request_logs_to_file(tmp_path):
    log_file = tmp_path / "api.log"
    client = TestClient(create_app(log_file=log_file))

    response = client.get("/health")

    assert response.status_code == 200
    log_text = log_file.read_text(encoding="utf-8")
    assert "GET /health -> 200" in log_text


def test_get_server_info_returns_backtest_storage_paths(tmp_path):
    client = _build_client(tmp_path)
    expected_results_dir = (tmp_path / "api-results").resolve()

    response = client.get("/server/info")

    assert response.status_code == 200
    body = response.json()
    assert body["backtest_results_dir"] == str(expected_results_dir)
    assert body["backtest_cache_dir"] == str((tmp_path / "cache").resolve())
    assert body["platform_settings_path"] == str(expected_results_dir / "settings" / "platform-settings.json")
    assert body["argo_workflows_enabled"] is False
    assert body["backtest_execution_backend"] == "local"


def test_get_settings_returns_defaults_when_file_missing(tmp_path):
    client = _build_client(tmp_path)

    response = client.get("/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["backtest_defaults"]["feed"] == "iex"
    assert body["backtest_defaults"]["analyzers"]["include_equity_curve"] is False
    assert body["backtest_defaults"]["analyzers"]["include_candidate_log"] is False
    assert body["backtest_defaults"]["analyzers"]["include_risk_auxiliary"] is False
    assert body["live_defaults"]["include_candidate_log"] is False
    assert body["platform_behavior"]["preferred_landing_page"] == "backtests"


def test_put_settings_persists_round_trip(tmp_path):
    client = _build_client(tmp_path)
    payload = client.get("/settings").json()
    payload["backtest_defaults"]["execution"]["fill_model"] = "next_bar"
    payload["backtest_defaults"]["analyzers"]["include_candidate_log"] = True
    payload["live_defaults"]["include_candidate_log"] = True
    payload["platform_behavior"]["timezone"] = "America/New_York"

    put_response = client.put("/settings", json=payload)
    get_response = client.get("/settings")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["backtest_defaults"]["execution"]["fill_model"] == "next_bar"
    assert get_response.json()["backtest_defaults"]["analyzers"]["include_candidate_log"] is True
    assert get_response.json()["live_defaults"]["include_candidate_log"] is True
    assert get_response.json()["platform_behavior"]["timezone"] == "America/New_York"


def test_put_settings_persists_results_table_columns(tmp_path):
    client = _build_client(tmp_path)
    payload = client.get("/settings").json()
    payload["backtest_defaults"]["results_table_columns"] = [
        "created",
        "status",
        "runtime",
        "runs",
    ]

    put_response = client.put("/settings", json=payload)
    get_response = client.get("/settings")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["backtest_defaults"]["results_table_columns"] == [
        "created",
        "status",
        "runtime",
        "runs",
    ]


def test_put_settings_rejects_invalid_results_table_columns(tmp_path):
    client = _build_client(tmp_path)
    payload = client.get("/settings").json()
    payload["backtest_defaults"]["results_table_columns"] = ["created", "not_a_column"]

    response = client.put("/settings", json=payload)

    assert response.status_code == 422
    assert "results_table_columns" in response.text or "Unknown results table column" in response.text


def test_put_settings_rejects_empty_results_table_columns(tmp_path):
    client = _build_client(tmp_path)
    payload = client.get("/settings").json()
    payload["backtest_defaults"]["results_table_columns"] = []

    response = client.put("/settings", json=payload)

    assert response.status_code == 422


def test_put_settings_rejects_invalid_execution_defaults(tmp_path):
    client = _build_client(tmp_path)
    payload = client.get("/settings").json()
    payload["backtest_defaults"]["execution"]["fill_model"] = "bad_model"

    response = client.put("/settings", json=payload)

    assert response.status_code == 422
    assert "fill_model" in response.text


def test_run_backtest_accepts_inline_yaml_and_writes_report(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/run",
        json={"config_text": yaml.safe_dump(_csv_backtest_payload()), "format": "yaml"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["total_runs"] == 1
    assert Path(body["output_path"]).is_absolute()
    output_path = Path(body["output_path"])
    assert output_path.parent.parent == (tmp_path / "api-results")
    assert output_path.parent.name == output_path.stem

    raw_report, report = _read_report(body["output_path"])
    assert report.status == "success"
    assert report.input_config_path is None
    result = raw_report["results"][0]
    assert "equity_curve" not in result
    assert "candidates" not in result
    assert "orders" not in result
    assert "trades" not in result
    assert "rejections" not in result
    stem = output_path.stem
    artifact_dir = output_path.parent
    assert (artifact_dir / f"{stem}.orders.parquet").exists()
    assert (artifact_dir / f"{stem}.trades.parquet").exists()


def test_run_backtest_accepts_inline_json(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/run",
        json={"config_text": json.dumps(_csv_backtest_payload()), "format": "json"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["successful_runs"] == 1
    assert Path(body["output_path"]).exists()


def test_run_backtest_invalid_json_returns_422(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/run",
        json={"config_text": '{"runs": [}', "format": "json"},
    )

    assert response.status_code == 422
    assert "Expecting value" in response.text


def test_run_backtest_invalid_yaml_returns_422(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/run",
        json={"config_text": "runs:\n  - [unclosed", "format": "yaml"},
    )

    assert response.status_code == 422
    assert "while parsing" in response.text


def test_run_backtest_invalid_config_returns_422(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/run",
        json={"config_text": json.dumps({"runs": []}), "format": "json"},
    )

    assert response.status_code == 422
    assert "At least one run is required" in response.text


def test_run_backtest_failure_report_still_returns_200(tmp_path):
    client = _build_client(tmp_path)
    payload = _csv_backtest_payload()
    payload["runs"].append(
        {
            "run_id": "missing_data",
            "start_date": "2024-01-01",
            "end_date": "2024-01-19",
            "data": {"type": "csv", "path": "examples/data/does-not-exist.csv"},
            "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
            "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
        }
    )

    response = client.post(
        "/backtests/run",
        json={"config_text": yaml.safe_dump(payload), "format": "yaml"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial_failure"
    assert body["failed_runs"] == 1


def test_run_backtest_write_failure_returns_500(tmp_path, monkeypatch):
    client = _build_client(tmp_path)

    def fail_write(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.api.routes.backtests_run.persist_backtest_report", fail_write)

    response = client.post(
        "/backtests/run",
        json={"config_text": json.dumps(_csv_backtest_payload()), "format": "json"},
    )

    assert response.status_code == 500
    assert "Failed to execute backtest" in response.text


def test_get_strategies_returns_all_built_in_strategies_and_parameter_metadata(tmp_path):
    client = TestClient(create_app(log_file=tmp_path / "api.log"))

    response = client.get("/strategies")

    assert response.status_code == 200
    triggers = response.json()
    assert [item["name"] for item in triggers] == [
        "sma_cross",
        "rsi_reversion",
        "buy_and_hold",
        "breakout_channel",
        "buy_oco_atr",
        "volume_rally",
        "fast_upswing",
    ]

    sma_cross = next(item for item in triggers if item["name"] == "sma_cross")
    assert sma_cross["parameters"]["fast"] == {
        "type": "integer",
        "default": 8,
        "required": False,
        "title": "Fast",
        "description": None,
        "enum": None,
        "multipleOf": None,
        "minimum": 2,
        "maximum": None,
        "exclusiveMinimum": None,
        "exclusiveMaximum": None,
        "minLength": None,
        "maxLength": None,
        "pattern": None,
    }

    exit_response = client.get("/strategies/exit-rules")
    assert exit_response.status_code == 200
    exit_rules = exit_response.json()
    assert any(item["name"] == "fixed_pct_oco" for item in exit_rules)
    fixed_pct = next(item for item in exit_rules if item["name"] == "fixed_pct_oco")
    assert "stop_loss_pct" not in fixed_pct["parameters"]
    assert "take_profit_pct" not in fixed_pct["parameters"]
    assert fixed_pct["parameters"]["atr_period"]["type"] == "integer"
    assert fixed_pct["parameters"]["sl_atr_mult"]["type"] == "number"
    assert fixed_pct["parameters"]["tp_atr_mult"]["type"] == "number"


def test_get_strategies_does_not_invent_cross_field_constraints(tmp_path):
    client = TestClient(create_app(log_file=tmp_path / "api.log"))

    response = client.get("/strategies")

    assert response.status_code == 200
    sma_cross = next(item for item in response.json() if item["name"] == "sma_cross")
    assert "fast must be smaller than slow" not in json.dumps(sma_cross)


def test_get_symbol_bars_success_and_cache_hit(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        return _FakeResponse(_mock_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)
    client = _build_client(tmp_path)

    params = {"start_date": "2024-01-01", "stop_date": "2024-01-03", "resolution": "1d"}
    first = client.get("/symbols/aapl/bars", params=params)
    second = client.get("/symbols/aapl/bars", params=params)

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls["n"] == 1
    assert first.json()["symbol"] == "AAPL"
    assert first.json()["provider"] == "alpaca"
    assert first.json()["cache_status"] == "miss"
    assert second.json()["cache_status"] == "hit"
    assert first.json()["rows"] == [
        {
            "timestamp": "2024-01-01T00:00:00+00:00",
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 1000.0,
        },
        {
            "timestamp": "2024-01-02T00:00:00+00:00",
            "open": 101.0,
            "high": 102.0,
            "low": 100.0,
            "close": 101.5,
            "volume": 1100.0,
        },
    ]


def test_get_symbol_bars_force_refresh_bypasses_cache(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(*args, **kwargs):
        calls["n"] += 1
        return _FakeResponse(_mock_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)
    client = _build_client(tmp_path)

    base_params = {"start_date": "2024-01-01", "stop_date": "2024-01-03", "resolution": "1d"}
    first = client.get("/symbols/AAPL/bars", params=base_params)
    refreshed = client.get("/symbols/AAPL/bars", params={**base_params, "force_refresh": "true"})

    assert first.status_code == 200
    assert refreshed.status_code == 200
    assert calls["n"] == 2
    assert refreshed.json()["cache_status"] == "force_refresh"


def test_get_symbol_bars_invalid_date_range_returns_422(tmp_path):
    client = _build_client(tmp_path)
    response = client.get(
        "/symbols/AAPL/bars",
        params={"start_date": "2024-01-03", "stop_date": "2024-01-01", "resolution": "1d"},
    )

    assert response.status_code == 422
    assert "start_date must be <=" in response.text


def test_get_symbol_bars_invalid_resolution_returns_422(tmp_path):
    client = _build_client(tmp_path)
    response = client.get(
        "/symbols/AAPL/bars",
        params={"start_date": "2024-01-01", "stop_date": "2024-01-03", "resolution": "2m"},
    )

    assert response.status_code == 422
    assert "resolution must be one of" in response.text


def test_get_symbol_bars_missing_credentials_returns_500(tmp_path, monkeypatch):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    client = _build_client(tmp_path)

    response = client.get(
        "/symbols/AAPL/bars",
        params={"start_date": "2024-01-01", "stop_date": "2024-01-03", "resolution": "1d"},
    )

    assert response.status_code == 500
    assert "Alpaca credentials missing" in response.text


def test_get_symbol_bars_no_data_returns_400(tmp_path, monkeypatch):
    def fake_urlopen(*args, **kwargs):
        return _FakeResponse(json.dumps({"bars": [], "next_page_token": None}).encode("utf-8"))

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)
    client = _build_client(tmp_path)

    response = client.get(
        "/symbols/AAPL/bars",
        params={"start_date": "2024-01-01", "stop_date": "2024-01-03", "resolution": "1d"},
    )

    assert response.status_code == 400
    assert "No Alpaca data found" in response.text


def test_create_trading_contract_persists_and_normalizes_symbol(tmp_path):
    client, session_factory = _build_contract_client(tmp_path)

    response = client.post(
        "/trading-contracts",
        json={
            "symbol": "aapl",
            "strategy": "sma_cross",
            "strategy_params": {"fast": 5, "slow": 10},
            "start_datetime": "2026-05-24T10:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 1000,
            "total_invested": 2500,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["symbol"] == "AAPL"
    assert body["strategy"] == "sma_cross"
    assert body["strategy_params"]["fast"] == 5

    with session_factory() as session:
        row_count = session.execute(text("SELECT COUNT(*) FROM trading_contracts")).scalar_one()
        stored_symbol = session.execute(text("SELECT symbol FROM trading_contracts")).scalar_one()
    assert row_count == 1
    assert stored_symbol == "AAPL"


def test_create_trading_contract_rejects_unknown_strategy(tmp_path):
    client, _ = _build_contract_client(tmp_path)

    response = client.post(
        "/trading-contracts",
        json={
            "symbol": "AAPL",
            "strategy": "missing_strategy",
            "strategy_params": {},
            "start_datetime": "2026-05-24T10:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 1000,
            "total_invested": 2500,
        },
    )

    assert response.status_code == 422
    assert "Unknown strategy" in response.text


def test_create_trading_contract_rejects_invalid_strategy_params(tmp_path):
    client, _ = _build_contract_client(tmp_path)

    response = client.post(
        "/trading-contracts",
        json={
            "symbol": "AAPL",
            "strategy": "sma_cross",
            "strategy_params": {"fast": 20, "slow": 10},
            "start_datetime": "2026-05-24T10:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 1000,
            "total_invested": 2500,
        },
    )

    assert response.status_code == 422
    assert "Invalid params for strategy 'sma_cross'" in response.text


def test_create_trading_contract_rejects_invalid_date_range(tmp_path):
    client, _ = _build_contract_client(tmp_path)

    response = client.post(
        "/trading-contracts",
        json={
            "symbol": "AAPL",
            "strategy": "sma_cross",
            "strategy_params": {"fast": 5, "slow": 10},
            "start_datetime": "2026-05-24T18:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 1000,
            "total_invested": 2500,
        },
    )

    assert response.status_code == 422
    assert "start_datetime must be < end_datetime" in response.text


def test_create_trading_contract_rejects_non_positive_maximum_trade_size(tmp_path):
    client, _ = _build_contract_client(tmp_path)

    response = client.post(
        "/trading-contracts",
        json={
            "symbol": "AAPL",
            "strategy": "sma_cross",
            "strategy_params": {"fast": 5, "slow": 10},
            "start_datetime": "2026-05-24T10:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 0,
            "total_invested": 2500,
        },
    )

    assert response.status_code == 422
    assert "greater than 0" in response.text


def test_get_active_trading_contracts_filters_and_honors_active_at(tmp_path):
    client, _ = _build_contract_client(tmp_path)
    payloads = [
        {
            "symbol": "AAPL",
            "strategy": "sma_cross",
            "strategy_params": {"fast": 5, "slow": 10},
            "start_datetime": "2026-05-24T10:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 1000,
            "total_invested": 2500,
        },
        {
            "symbol": "MSFT",
            "strategy": "rsi_reversion",
            "strategy_params": {"period": 7, "oversold": 30, "overbought": 70},
            "start_datetime": "2026-05-24T14:00:00+00:00",
            "end_datetime": "2026-05-24T20:00:00+00:00",
            "maximum_trade_size": 2000,
            "total_invested": 3000,
        },
        {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "strategy_params": {"stake": 1},
            "start_datetime": "2026-05-24T05:00:00+00:00",
            "end_datetime": "2026-05-24T12:00:00+00:00",
            "maximum_trade_size": 500,
            "total_invested": 900,
        },
    ]
    for payload in payloads:
        create_response = client.post("/trading-contracts", json=payload)
        assert create_response.status_code == 201

    response = client.get("/trading-contracts/active", params={"active_at": "2026-05-24T15:00:00+00:00"})
    assert response.status_code == 200
    body = response.json()
    assert [item["symbol"] for item in body] == ["AAPL", "MSFT"]

    symbol_response = client.get(
        "/trading-contracts/active",
        params={"active_at": "2026-05-24T15:00:00+00:00", "symbol": "aapl"},
    )
    assert symbol_response.status_code == 200
    assert [item["strategy"] for item in symbol_response.json()] == ["sma_cross"]

    strategy_response = client.get(
        "/trading-contracts/active",
        params={"active_at": "2026-05-24T15:00:00+00:00", "strategy": "rsi_reversion"},
    )
    assert strategy_response.status_code == 200
    assert [item["symbol"] for item in strategy_response.json()] == ["MSFT"]

    combined_response = client.get(
        "/trading-contracts/active",
        params={"active_at": "2026-05-24T15:00:00+00:00", "symbol": "AAPL", "strategy": "sma_cross"},
    )
    assert combined_response.status_code == 200
    assert len(combined_response.json()) == 1


def _single_day_alpaca_payload() -> bytes:
    payload = {
        "bars": [
            {"t": "2024-01-15T14:30:00Z", "o": 100.0, "h": 101.0, "l": 99.0, "c": 100.5, "v": 1000},
            {"t": "2024-01-15T14:31:00Z", "o": 100.5, "h": 102.0, "l": 100.0, "c": 101.5, "v": 1100},
            {"t": "2024-01-15T14:32:00Z", "o": 101.5, "h": 103.0, "l": 101.0, "c": 102.0, "v": 1200},
        ],
        "next_page_token": None,
    }
    return json.dumps(payload).encode("utf-8")


def _single_day_request(**overrides) -> dict[str, object]:
    payload = {
        "symbol": "AAPL",
        "date": "2024-01-15",
        "resolution": "1m",
        "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
        "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
    }
    payload.update(overrides)
    return payload


def test_run_single_day_backtest_success(tmp_path, monkeypatch):
    def fake_urlopen(*args, **kwargs):
        return _FakeResponse(_single_day_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)
    client = _build_client(tmp_path)

    response = client.post("/backtests/single-day", json=_single_day_request())

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "AAPL"
    assert body["date"] == "2024-01-15"
    assert body["resolution"] == "1m"
    assert body["cache_status"] == "miss"
    assert len(body["bars"]) == 3
    assert body["backtest"]["status"] == "success"
    assert body["backtest"]["summary"] is not None
    assert body["backtest"]["summary"]["total_trades"] >= 0
    assert len(body["backtest"]["orders"]) >= 1
    assert body["backtest"]["orders"][0]["is_buy"] is True
    assert body["backtest"]["error"] is None


def test_run_single_day_backtest_unknown_strategy_returns_422(tmp_path, monkeypatch):
    def fake_urlopen(*args, **kwargs):
        return _FakeResponse(_single_day_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/single-day",
        json=_single_day_request(trigger={"name": "missing_trigger", "params": {}}),
    )

    assert response.status_code == 422
    assert "Unknown trigger" in response.text


def test_run_single_day_backtest_invalid_strategy_params_returns_422(tmp_path, monkeypatch):
    def fake_urlopen(*args, **kwargs):
        return _FakeResponse(_single_day_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/single-day",
        json=_single_day_request(trigger={"name": "sma_cross", "params": {"fast": 20, "slow": 10, "stake": 1}}),
    )

    assert response.status_code == 422
    assert "Invalid params for trigger 'sma_cross'" in response.text


def test_run_single_day_backtest_invalid_resolution_returns_422(tmp_path):
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/single-day",
        json=_single_day_request(resolution="2m"),
    )

    assert response.status_code == 422
    assert "resolution must be one of" in response.text


def test_run_single_day_backtest_returns_bars_when_backtest_fails(tmp_path, monkeypatch):
    from datetime import datetime, timezone

    def fake_urlopen(*args, **kwargs):
        return _FakeResponse(_single_day_alpaca_payload())

    def fake_run_backtests(config, config_raw):
        return BacktestReport(
            generated_at=datetime.now(timezone.utc),
            app_version="test",
            config_sha256="abc",
            input_config=config_raw,
            total_runs=1,
            successful_runs=0,
            failed_runs=1,
            status="failure",
            results=[
                {
                    "run_id": "ui_AAPL_2024-01-15",
                    "status": "failed",
                    "strategy": "buy_and_hold",
                    "data_source": "alpaca",
                    "error": {"type": "RuntimeError", "message": "simulated failure"},
                }
            ],
        )

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)
    monkeypatch.setattr("app.api.routes.backtests_run.run_backtests", fake_run_backtests)
    client = _build_client(tmp_path)

    response = client.post("/backtests/single-day", json=_single_day_request())

    assert response.status_code == 200
    body = response.json()
    assert len(body["bars"]) == 3
    assert body["backtest"]["status"] == "failed"
    assert body["backtest"]["error"]["message"] == "simulated failure"


def test_list_trading_contracts_returns_all_ordered_and_filters(tmp_path):
    client, _ = _build_contract_client(tmp_path)
    payloads = [
        {
            "symbol": "AAPL",
            "strategy": "sma_cross",
            "strategy_params": {"fast": 5, "slow": 10},
            "start_datetime": "2026-05-24T10:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 1000,
            "total_invested": 2500,
        },
        {
            "symbol": "MSFT",
            "strategy": "rsi_reversion",
            "strategy_params": {"period": 7, "oversold": 30, "overbought": 70},
            "start_datetime": "2026-05-24T14:00:00+00:00",
            "end_datetime": "2026-05-24T20:00:00+00:00",
            "maximum_trade_size": 2000,
            "total_invested": 3000,
        },
        {
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "strategy_params": {"stake": 1},
            "start_datetime": "2026-05-24T05:00:00+00:00",
            "end_datetime": "2026-05-24T12:00:00+00:00",
            "maximum_trade_size": 500,
            "total_invested": 900,
        },
    ]
    for payload in payloads:
        create_response = client.post("/trading-contracts", json=payload)
        assert create_response.status_code == 201

    response = client.get("/trading-contracts")
    assert response.status_code == 200
    body = response.json()
    assert [item["symbol"] for item in body] == ["MSFT", "AAPL", "AAPL"]
    assert [item["strategy"] for item in body] == ["rsi_reversion", "sma_cross", "buy_and_hold"]

    symbol_response = client.get("/trading-contracts", params={"symbol": "aapl"})
    assert symbol_response.status_code == 200
    assert [item["strategy"] for item in symbol_response.json()] == ["sma_cross", "buy_and_hold"]

    strategy_response = client.get("/trading-contracts", params={"strategy": "rsi_reversion"})
    assert strategy_response.status_code == 200
    assert [item["symbol"] for item in strategy_response.json()] == ["MSFT"]


def test_get_active_trading_contracts_excludes_end_boundary(tmp_path):
    client, _ = _build_contract_client(tmp_path)

    create_response = client.post(
        "/trading-contracts",
        json={
            "symbol": "AAPL",
            "strategy": "buy_and_hold",
            "strategy_params": {"stake": 1},
            "start_datetime": "2026-05-24T10:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 1000,
            "total_invested": 2500,
        },
    )
    assert create_response.status_code == 201

    response = client.get("/trading-contracts/active", params={"active_at": "2026-05-24T16:00:00+00:00"})
    assert response.status_code == 200
    assert response.json() == []


def _create_sample_contract(client, *, symbol: str = "AAPL", strategy: str = "sma_cross") -> dict:
    response = client.post(
        "/trading-contracts",
        json={
            "symbol": symbol,
            "strategy": strategy,
            "strategy_params": {"fast": 5, "slow": 10} if strategy == "sma_cross" else {"stake": 1},
            "start_datetime": "2026-05-24T10:00:00+00:00",
            "end_datetime": "2026-05-24T16:00:00+00:00",
            "maximum_trade_size": 1000,
            "total_invested": 2500,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_update_trading_contract_bumps_revision_and_invalidates_assignments(tmp_path, monkeypatch):
    from app.contract_mutations import reset_contract_mutation_service
    from app.live.assignments import get_shared_redis_backend

    monkeypatch.setenv("LIVE_REDIS_URL", "memory://api-update-contract")
    reset_contract_mutation_service()
    client, _ = _build_contract_client(tmp_path)
    created = _create_sample_contract(client)
    backend = get_shared_redis_backend("memory://api-update-contract")

    response = client.patch(
        f"/trading-contracts/{created['id']}",
        json={"maximum_trade_size": 1500, "total_invested": 3000},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["maximum_trade_size"] == 1500
    assert body["total_invested"] == 3000
    assert body["revision"] == 2
    assert backend.get("ta:control:revoked:contract:" + created["id"]) is not None
    assert int(backend.get("ta:assignments:version")) >= 1


def test_delete_trading_contract_soft_deletes_and_bumps_assignments(tmp_path, monkeypatch):
    from app.contract_mutations import reset_contract_mutation_service
    from app.live.assignments import get_shared_redis_backend

    monkeypatch.setenv("LIVE_REDIS_URL", "memory://api-delete-contract")
    reset_contract_mutation_service()
    client, _ = _build_contract_client(tmp_path)
    created = _create_sample_contract(client)
    backend = get_shared_redis_backend("memory://api-delete-contract")

    delete_response = client.delete(f"/trading-contracts/{created['id']}")
    assert delete_response.status_code == 200
    deleted_body = delete_response.json()
    assert deleted_body["deleted_at"] is not None
    assert deleted_body["revision"] == 2

    list_response = client.get("/trading-contracts")
    assert list_response.status_code == 200
    assert list_response.json() == []

    active_response = client.get(
        "/trading-contracts/active",
        params={"active_at": "2026-05-24T12:00:00+00:00"},
    )
    assert active_response.status_code == 200
    assert active_response.json() == []

    second_delete = client.delete(f"/trading-contracts/{created['id']}")
    assert second_delete.status_code == 404
    assert backend.get("ta:control:revoked:contract:" + created["id"]) is not None


def test_update_deleted_trading_contract_returns_not_found(tmp_path, monkeypatch):
    from app.contract_mutations import reset_contract_mutation_service

    monkeypatch.setenv("LIVE_REDIS_URL", "memory://api-update-deleted")
    reset_contract_mutation_service()
    client, _ = _build_contract_client(tmp_path)
    created = _create_sample_contract(client)
    assert client.delete(f"/trading-contracts/{created['id']}").status_code == 200

    response = client.patch(
        f"/trading-contracts/{created['id']}",
        json={"maximum_trade_size": 1200},
    )
    assert response.status_code == 404


def test_get_live_runtime_returns_redis_state_and_postgres_events(tmp_path):
    client, session_factory, stores = _build_live_runtime_client(tmp_path)
    now = datetime.now(UTC)

    stores.assignment_store.publish_assignments(2, {0: {"AAPL@1m"}, 1: {"MSFT@1m"}})
    stores.assignment_store.set_worker_heartbeat(
        heartbeat_from_runtime(
            worker_id="worker-0",
            pod_name="pod-0",
            shard_id=0,
            status=RuntimeContractState.TRADABLE,
            owned_symbol_count=1,
            updated_at=now,
        )
    )
    stores.lease_store.acquire_symbol_lease(
        LeaseAcquireRequest(
            worker_id="worker-0",
            pod_name="pod-0",
            shard_id=0,
            symbol_key="AAPL@1m",
            assignment_version=2,
            leased_at=now,
            expires_at=now + timedelta(minutes=5),
        )
    )
    stores.control_flag_store.backend.set("ta:control:kill_switch", '{"enabled": true}')
    stores.control_flag_store.backend.set('ta:control:pause:symbol:AAPL@1m', '{"enabled": true}')

    with session_factory() as session:
        session.add(
            WorkerEvent(
                worker_id="controller",
                event_type="controller_sync",
                severity="info",
                payload={"assignment_version": 2},
                created_at=now - timedelta(minutes=1),
            )
        )
        session.add(
            WorkerEvent(
                worker_id="worker-0",
                shard_id=0,
                symbol_key="AAPL@1m",
                event_type="lease_acquired",
                severity="info",
                payload={"symbol_key": "AAPL@1m"},
                created_at=now,
            )
        )
        session.add(
            WorkerEvent(
                worker_id="reconciler",
                event_type="reconciliation_run",
                severity="info",
                payload={"status": "completed"},
                created_at=now - timedelta(minutes=2),
            )
        )
        session.commit()

    response = client.get("/live/runtime")
    assert response.status_code == 200
    body = response.json()

    assert body["state"]["assignment_version"] == 2
    assert body["state"]["assignments"] == [
        {"shard_id": 0, "symbol_keys": ["AAPL@1m"]},
        {"shard_id": 1, "symbol_keys": ["MSFT@1m"]},
    ]
    assert len(body["state"]["workers"]) == 1
    assert body["state"]["workers"][0]["worker_id"] == "worker-0"
    assert body["state"]["workers"][0]["status"] == "tradable"
    assert len(body["state"]["leases"]) == 1
    assert body["state"]["leases"][0]["symbol_key"] == "AAPL@1m"
    assert body["state"]["control_flags"]["kill_switch_enabled"] is True
    assert body["state"]["control_flags"]["paused_symbols"] == ["AAPL@1m"]

    assert len(body["events"]) == 3
    assert body["events"][0]["event_type"] == "lease_acquired"
    assert body["events"][1]["event_type"] == "controller_sync"
    assert body["events"][2]["event_type"] == "reconciliation_run"


def test_get_live_runtime_filters_events_by_worker_id(tmp_path):
    client, session_factory, _stores = _build_live_runtime_client(tmp_path)
    now = datetime.now(UTC)

    with session_factory() as session:
        session.add(
            WorkerEvent(
                worker_id="controller",
                event_type="controller_sync",
                severity="info",
                payload={},
                created_at=now,
            )
        )
        session.add(
            WorkerEvent(
                worker_id="worker-0",
                event_type="worker_started",
                severity="info",
                payload={},
                created_at=now - timedelta(seconds=1),
            )
        )
        session.commit()

    response = client.get("/live/runtime", params={"worker_id": "controller", "limit": 10})
    assert response.status_code == 200
    body = response.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["worker_id"] == "controller"


class _FakeArgoSubmitter:
    def __init__(self, configured: bool = True) -> None:
        self.configured = configured
        self.last_submit: dict[str, str] | None = None

    @property
    def is_configured(self) -> bool:
        return self.configured

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

    def get_workflow(self, workflow_name: str) -> dict | None:
        del workflow_name
        return {"status": {"phase": "Running", "progress": "0/1", "nodes": {}}}

    def get_workflow_phase(self, workflow_name: str) -> str | None:
        del workflow_name
        return "Running"


def test_launch_argo_backtest_with_inline_config(tmp_path):
    client = _build_client(tmp_path)
    fake = _FakeArgoSubmitter()
    client.app.state.deps.backtest_jobs.argo_submitter = fake

    config_text = yaml.safe_dump(
        {
            "runs": [
                {
                    "run_id": "csv_ok",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-19",
                    "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                    "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                    "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
                }
            ]
        }
    )
    response = client.post(
        "/backtests/argo",
        json={"config_text": config_text, "format": "yaml", "split_by": "run"},
    )

    assert response.status_code == 202
    body = response.json()
    assert body["workflow_name"].startswith("backtest-")
    assert body["workflow_namespace"] == "backtest-workflows"
    assert body["status"] == "running"
    assert fake.last_submit is not None
    assert fake.last_submit["split_by"] == "run"
    assert fake.last_submit["config_yaml"] is not None
    assert "runs:" in fake.last_submit["config_yaml"]

    status = client.get(f"/backtests/{body['backtest_id']}/status")
    assert status.status_code == 200
    status_body = status.json()
    assert status_body["execution_backend"] == "argo"
    assert status_body["workflow_name"] == body["workflow_name"]
    assert status_body["progress_pct"] == 0.0
    assert status_body["is_terminal"] is False


def test_launch_argo_backtest_with_config_path(tmp_path):
    client = _build_client(tmp_path)
    fake = _FakeArgoSubmitter()
    client.app.state.deps.backtest_jobs.argo_submitter = fake
    results_dir = tmp_path / "api-results"
    config_path = results_dir / "experiment.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "runs": [
                    {
                        "run_id": "csv_ok",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                        "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    response = client.post("/backtests/argo", json={"config_path": str(config_path)})

    assert response.status_code == 202
    assert fake.last_submit is not None
    assert fake.last_submit["config_path"].startswith("/data/backtest-results/")
    assert fake.last_submit["config_yaml"] is not None
    assert "csv_ok" in fake.last_submit["config_yaml"]


def test_workflow_artifact_paths_ignore_api_results_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_RESULTS_DIR", str(tmp_path / "local-results"))
    from app.backtests.argo_workflow import workflow_artifact_paths

    config_path, output_path = workflow_artifact_paths("job123")
    assert config_path == "/data/backtest-results/job123/job123.yaml"
    assert output_path == "/data/backtest-results/job123/job123.json"


def test_workflow_artifact_paths_honor_workflow_mount_override(monkeypatch):
    monkeypatch.setenv("BACKTEST_WORKFLOW_RESULTS_MOUNT", "/mnt/shared/results")
    from app.backtests.argo_workflow import workflow_artifact_paths

    config_path, output_path = workflow_artifact_paths("job123")
    assert config_path == "/mnt/shared/results/job123/job123.yaml"
    assert output_path == "/mnt/shared/results/job123/job123.json"


def test_launch_argo_backtest_uses_workflow_mount_when_api_results_dir_differs(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_RESULTS_DIR", str(tmp_path / "local-results"))
    client = _build_client(tmp_path)
    fake = _FakeArgoSubmitter()
    client.app.state.deps.backtest_jobs.argo_submitter = fake

    config_text = yaml.safe_dump(
        {
            "runs": [
                {
                    "run_id": "csv_ok",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-19",
                    "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                    "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                    "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
                }
            ]
        }
    )
    response = client.post(
        "/backtests/argo",
        json={"config_text": config_text, "format": "yaml"},
    )

    assert response.status_code == 202
    assert fake.last_submit is not None
    backtest_id = fake.last_submit["backtest_id"]
    assert fake.last_submit["output_path"] == f"/data/backtest-results/{backtest_id}/{backtest_id}.json"


def test_launch_argo_backtest_rejects_unshared_results_when_required(tmp_path, monkeypatch):
    monkeypatch.setenv("BACKTEST_RESULTS_DIR", str(tmp_path / "local-results"))
    monkeypatch.setenv("ARGO_REQUIRE_SHARED_RESULTS", "1")
    client = _build_client(tmp_path)
    client.app.state.deps.backtest_jobs.argo_submitter = _FakeArgoSubmitter()

    config_text = yaml.safe_dump(
        {
            "runs": [
                {
                    "run_id": "csv_ok",
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-19",
                    "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                    "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                    "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
                }
            ]
        }
    )
    response = client.post(
        "/backtests/argo",
        json={"config_text": config_text, "format": "yaml"},
    )

    assert response.status_code == 503
    assert "Argo workflows write results under" in response.json()["detail"]


def test_get_detail_loads_report_from_db_paths(tmp_path):
    client = _build_client(tmp_path)
    jobs = client.app.state.deps.backtest_jobs
    backtest_id = "db-path-test-id"
    external_dir = tmp_path / "shared-results"
    external_dir.mkdir()
    report_path = external_dir / f"{backtest_id}.json"
    report = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="abc123",
        input_config={"backtest_id": backtest_id},
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[],
    )
    report_path.write_text(report.model_dump_json(), encoding="utf-8")

    from app.backtests.persistence import BacktestArtifactPaths

    jobs.job_repository.create(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="completed",
            report_status="success",
            total_runs=1,
            completed_runs=1,
            successful_runs=1,
            failed_runs=0,
            execution_backend="argo",
            workflow_name="backtest-db-path-test",
            workflow_namespace="backtest-workflows",
        ),
        paths=BacktestArtifactPaths(report_json_path=str(report_path.resolve())),
    )

    detail = client.get(f"/backtests/{backtest_id}").json()
    assert detail["report"] is not None
    assert detail["report"]["total_runs"] == 1
    assert detail["output_path"] == str(report_path.resolve())


def test_get_detail_ignores_embedded_legacy_trades_json(tmp_path):
    client = _build_client(tmp_path)
    backtest_id = "legacy-trades"
    report_path = tmp_path / "external" / f"{backtest_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="1.0",
        config_sha256="abc",
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[
            RunResult(
                run_id="r1",
                status="success",
                strategy="sma_cross",
                symbol="AAPL",
                data_source="csv",
                summary=RunSummary(
                    start_value=10000.0,
                    end_value=10010.0,
                    return_pct=0.1,
                    total_trades=1,
                    won_trades=1,
                    lost_trades=0,
                ),
                trades=[
                    TradeRecord(
                        datetime="2024-01-02T00:00:00+00:00",
                        size=1.0,
                        price=100.0,
                        value=100.0,
                        pnl=10.0,
                        pnlcomm=10.0,
                        reason="legacy_json",
                    )
                ],
            )
        ],
    )
    report_path.write_text(report.model_dump_json(), encoding="utf-8")

    metadata = BacktestListItem(
        id=backtest_id,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        status="completed",
        total_runs=1,
        completed_runs=1,
        successful_runs=1,
        failed_runs=0,
        report_status="success",
    )
    client.app.state.deps.backtest_jobs.job_repository.create(
        metadata,
        paths=BacktestArtifactPaths(report_json_path=str(report_path.resolve())),
    )

    detail = client.get(f"/backtests/{backtest_id}").json()

    assert detail["report"] is not None
    assert detail["report"]["results"][0]["trades"] == []


def test_get_detail_falls_back_to_output_dir_when_db_path_missing(tmp_path):
    client = _build_client(tmp_path)
    jobs = client.app.state.deps.backtest_jobs
    backtest_id = "argo-fallback-path-test"
    report = BacktestReport(
        generated_at=datetime.now(UTC),
        app_version="0.1.0",
        config_sha256="abc123",
        input_config={"backtest_id": backtest_id},
        total_runs=1,
        successful_runs=1,
        failed_runs=0,
        status="success",
        results=[],
    )
    jobs.repository.save_report(backtest_id, report)
    local_report_path = jobs.repository.report_path(backtest_id)

    from app.backtests.persistence import BacktestArtifactPaths

    jobs.job_repository.create(
        BacktestListItem(
            id=backtest_id,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            status="completed",
            report_status="success",
            total_runs=1,
            completed_runs=1,
            successful_runs=1,
            failed_runs=0,
            execution_backend="argo",
            workflow_name="backtest-argo-fallback-path-test",
            workflow_namespace="backtest-workflows",
        ),
        paths=BacktestArtifactPaths(
            report_json_path=f"/data/backtest-results/{backtest_id}/{backtest_id}.json",
        ),
    )

    detail = client.get(f"/backtests/{backtest_id}").json()
    assert detail["report"] is not None
    assert detail["report"]["total_runs"] == 1
    assert detail["output_path"] == str(local_report_path.resolve())


def test_launch_argo_backtest_returns_503_when_unconfigured(tmp_path):
    client = _build_client(tmp_path)
    client.app.state.deps.backtest_jobs.argo_submitter = _FakeArgoSubmitter(configured=False)

    response = client.post(
        "/backtests/argo",
        json={
            "config_text": "runs: []\n",
            "format": "yaml",
        },
    )

    assert response.status_code == 503


def test_launch_argo_backtest_missing_config_path_returns_404(tmp_path):
    client = _build_client(tmp_path)
    client.app.state.deps.backtest_jobs.argo_submitter = _FakeArgoSubmitter()

    response = client.post("/backtests/argo", json={"config_path": "/missing/config.yaml"})

    assert response.status_code == 404


def test_relaunch_argo_backtest_for_existing_config(tmp_path):
    client = _build_client(tmp_path)
    fake = _FakeArgoSubmitter()
    client.app.state.deps.backtest_jobs.argo_submitter = fake
    backtest_id = "abc123"
    config_path = tmp_path / "api-results" / backtest_id / f"{backtest_id}.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        yaml.safe_dump(
            {
                "runs": [
                    {
                        "run_id": "csv_ok",
                        "start_date": "2024-01-01",
                        "end_date": "2024-01-19",
                        "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                        "trigger": {"name": "buy_and_hold", "params": {"stake": 1}},
                        "exit_rules": {"rules": [{"name": "max_hold_bars", "params": {"max_hold_bars": 10_000}}]},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    response = client.post(f"/backtests/{backtest_id}/argo")

    assert response.status_code == 202
    assert response.json()["backtest_id"] == backtest_id
    assert fake.last_submit is not None
    assert fake.last_submit["backtest_id"] == backtest_id
