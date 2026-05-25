from __future__ import annotations

import json
from pathlib import Path

import yaml

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from datetime import datetime

from app.api import create_app
from app.api_logging import build_timestamped_log_file
from app.config.models import DataCacheConfig
from app.db.base import Base
from app.db.session import get_db_session
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


def test_get_settings_returns_defaults_when_file_missing(tmp_path):
    client = _build_client(tmp_path)

    response = client.get("/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["backtest_defaults"]["feed"] == "iex"
    assert body["backtest_defaults"]["analyzers"]["include_equity_curve"] is False
    assert body["platform_behavior"]["preferred_landing_page"] == "backtests"


def test_put_settings_persists_round_trip(tmp_path):
    client = _build_client(tmp_path)
    payload = client.get("/settings").json()
    payload["backtest_defaults"]["execution"]["fill_model"] = "next_bar"
    payload["platform_behavior"]["timezone"] = "America/New_York"

    put_response = client.put("/settings", json=payload)
    get_response = client.get("/settings")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    assert get_response.json()["backtest_defaults"]["execution"]["fill_model"] == "next_bar"
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

    monkeypatch.setattr("app.api.write_backtest_report_json", fail_write)

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
    monkeypatch.setattr("app.api.run_backtests", fake_run_backtests)
    client = _build_client(tmp_path)

    response = client.post("/backtests/single-day", json=_single_day_request())

    assert response.status_code == 200
    body = response.json()
    assert len(body["bars"]) == 3
    assert body["backtest"]["status"] == "failed"
    assert body["backtest"]["error"]["message"] == "simulated failure"


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
