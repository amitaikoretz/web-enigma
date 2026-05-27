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
from app.output.models import BacktestReport


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
    app = create_app(
        DataCacheConfig(directory=str(tmp_path)),
        output_dir=tmp_path / "api-results",
        log_file=tmp_path / "api.log",
    )
    return TestClient(app)


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
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
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
    assert body["backtest_cache_dir"] == str(tmp_path.resolve())
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
    assert Path(body["output_path"]).parent == (tmp_path / "api-results")

    raw_report, report = _read_report(body["output_path"])
    assert report.status == "success"
    assert report.input_config_path is None
    assert "equity_curve" not in raw_report["results"][0]


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
            "strategy": "buy_and_hold",
            "strategy_params": {"stake": 1},
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

    monkeypatch.setattr("app.api.routes.backtests_run.write_backtest_report_json", fail_write)

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
    body = response.json()
    assert [item["name"] for item in body] == [
        "sma_cross",
        "rsi_reversion",
        "buy_and_hold",
        "breakout_channel",
        "buy_oco_atr_tp_sl",
        "buy_oco_atr_tp_trailing",
        "volume_rally",
    ]

    sma_cross = next(item for item in body if item["name"] == "sma_cross")
    assert sma_cross["description"] == "Intraday SMA momentum with fixed stop-loss and take-profit."
    assert sma_cross["parameters"]["fast"] == {
        "type": "integer",
        "default": 8,
        "required": False,
        "minimum": 2,
        "maximum": None,
        "exclusiveMinimum": None,
        "exclusiveMaximum": None,
        "minLength": None,
        "maxLength": None,
        "pattern": None,
    }
    assert sma_cross["parameters"]["stop_loss_pct"]["exclusiveMinimum"] == 0
    assert sma_cross["parameters"]["stop_loss_pct"]["exclusiveMaximum"] == 0.5


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
        "strategy": "buy_and_hold",
        "strategy_params": {"stake": 1},
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
        json=_single_day_request(strategy="missing_strategy"),
    )

    assert response.status_code == 422
    assert "Unknown strategy" in response.text


def test_run_single_day_backtest_invalid_strategy_params_returns_422(tmp_path, monkeypatch):
    def fake_urlopen(*args, **kwargs):
        return _FakeResponse(_single_day_alpaca_payload())

    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    monkeypatch.setattr("app.data.loaders.urlopen", fake_urlopen)
    client = _build_client(tmp_path)

    response = client.post(
        "/backtests/single-day",
        json=_single_day_request(strategy="sma_cross", strategy_params={"fast": 20, "slow": 10}),
    )

    assert response.status_code == 422
    assert "Invalid params for strategy 'sma_cross'" in response.text


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
        return f"backtest-{backtest_id[:8]}", "backtest"

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
                    "strategy": "buy_and_hold",
                    "strategy_params": {"stake": 1},
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
    assert body["workflow_namespace"] == "backtest"
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
                        "strategy": "buy_and_hold",
                        "strategy_params": {"stake": 1},
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
    config_path = tmp_path / "api-results" / f"{backtest_id}.yaml"
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
                        "strategy": "buy_and_hold",
                        "strategy_params": {"stake": 1},
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

