from __future__ import annotations

import time

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api import create_app
from app.config.models import DataCacheConfig


def _build_client(tmp_path, *, cache_dir: str | None = None) -> TestClient:
    directory = cache_dir or str(tmp_path / "cache")
    return TestClient(
        create_app(
            cache_config=DataCacheConfig(directory=directory),
            output_dir=tmp_path / "api-results",
            log_file=tmp_path / "api.log",
        )
    )


def _download_payload(output_folder: str, *, symbols: list[str] | None = None) -> dict[str, object]:
    symbols = symbols or ["AAPL"]
    return {
        "output_folder": output_folder,
        "records": [
            {
                "symbol": symbol,
                "start_date": "2024-01-01",
                "stop_date": "2024-01-31",
                "resolution": "1d",
                "feed": "iex",
            }
            for symbol in symbols
        ],
    }


def _wait_for_terminal_status(client: TestClient, job_id: str, timeout: float = 5.0) -> dict[str, object]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        response = client.get(f"/market-data/downloads/{job_id}/status")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in {"completed", "failed"}:
            return body
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for data download job {job_id} to finish")


def _mock_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.0, 100.0],
            "Close": [100.5, 101.5],
            "Volume": [1000.0, 1100.0],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )


def test_data_download_happy_path(tmp_path, monkeypatch):
    client = _build_client(tmp_path)
    cache_dir = tmp_path / "cache"
    calls: list[tuple] = []

    def fake_loader(config, start_date, end_date, cache_config, force_refresh=False):
        calls.append((config.symbol, start_date, end_date, cache_config.directory, force_refresh))
        return _mock_frame(), "miss"

    monkeypatch.setattr("app.data.downloads.service.build_alpaca_data_feed_with_cache", fake_loader)

    response = client.post("/market-data/downloads", json=_download_payload(str(cache_dir)))
    assert response.status_code == 202
    body = response.json()
    job_id = body["job_id"]
    assert body["status"] == "pending"
    assert body["status_url"] == f"/market-data/downloads/{job_id}/status"

    status = _wait_for_terminal_status(client, job_id)
    assert status["status"] == "completed"
    assert status["total_records"] == 1
    assert status["successful_records"] == 1
    assert status["failed_records"] == 0

    detail = client.get(f"/market-data/downloads/{job_id}")
    assert detail.status_code == 200
    record = detail.json()["records"][0]
    assert record["symbol"] == "AAPL"
    assert record["cache_status"] == "miss"
    assert record["row_count"] == 2
    assert record["parquet_path"].endswith(".parquet")
    assert record["error"] is None
    assert calls[0][3] == str(cache_dir.resolve())


def test_data_download_rejects_invalid_resolution(tmp_path):
    client = _build_client(tmp_path)
    payload = _download_payload(str(tmp_path / "cache"))
    payload["records"][0]["resolution"] = "2m"

    response = client.post("/market-data/downloads", json=payload)
    assert response.status_code == 422


def test_data_download_rejects_inverted_dates(tmp_path):
    client = _build_client(tmp_path)
    payload = _download_payload(str(tmp_path / "cache"))
    payload["records"][0]["start_date"] = "2024-02-01"
    payload["records"][0]["stop_date"] = "2024-01-01"

    response = client.post("/market-data/downloads", json=payload)
    assert response.status_code == 422


def test_data_download_rejects_output_folder_outside_allowed_root(tmp_path):
    client = _build_client(tmp_path)

    response = client.post("/market-data/downloads", json=_download_payload("/tmp/outside-cache"))
    assert response.status_code == 422
    assert "allowed cache root" in response.json()["detail"]


def test_data_download_partial_failure(tmp_path, monkeypatch):
    client = _build_client(tmp_path)
    cache_dir = tmp_path / "cache"

    def fake_loader(config, start_date, end_date, cache_config, force_refresh=False):
        if config.symbol == "BAD":
            raise RuntimeError("No Alpaca data found for symbol BAD")
        return _mock_frame(), "miss"

    monkeypatch.setattr("app.data.downloads.service.build_alpaca_data_feed_with_cache", fake_loader)

    response = client.post(
        "/market-data/downloads",
        json=_download_payload(str(cache_dir), symbols=["AAPL", "BAD"]),
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    status = _wait_for_terminal_status(client, job_id)
    assert status["status"] == "completed"
    assert status["successful_records"] == 1
    assert status["failed_records"] == 1

    detail = client.get(f"/market-data/downloads/{job_id}")
    records = {item["symbol"]: item for item in detail.json()["records"]}
    assert records["AAPL"]["error"] is None
    assert records["BAD"]["error"] == "No Alpaca data found for symbol BAD"


def test_data_download_list_and_not_found(tmp_path, monkeypatch):
    client = _build_client(tmp_path)
    cache_dir = tmp_path / "cache"

    monkeypatch.setattr(
        "app.data.downloads.service.build_alpaca_data_feed_with_cache",
        lambda *args, **kwargs: (_mock_frame(), "miss"),
    )

    create = client.post("/market-data/downloads", json=_download_payload(str(cache_dir)))
    job_id = create.json()["job_id"]
    _wait_for_terminal_status(client, job_id)

    listed = client.get("/market-data/downloads")
    assert listed.status_code == 200
    assert any(item["job_id"] == job_id for item in listed.json())

    missing = client.get("/market-data/downloads/does-not-exist/status")
    assert missing.status_code == 404


def test_create_app_uses_backtest_cache_dir_env(tmp_path, monkeypatch):
    cache_root = tmp_path / "env-cache"
    cache_root.mkdir()
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(cache_root))

    app = create_app(output_dir=tmp_path / "api-results", log_file=tmp_path / "api.log")
    assert app.state.deps.cache_config.directory == str(cache_root)


def test_resolve_output_folder_allows_env_cache_root(tmp_path, monkeypatch):
    from app.data.downloads.service import resolve_output_folder

    cache_root = tmp_path / "env-cache"
    cache_root.mkdir()
    monkeypatch.setenv("BACKTEST_CACHE_DIR", str(cache_root))

    resolved = resolve_output_folder(str(cache_root / "nested"), DataCacheConfig(directory=str(tmp_path / "other")))
    assert resolved == (cache_root / "nested").resolve()


def test_resolve_output_folder_rejects_outside_roots(tmp_path):
    from app.data.downloads.service import InvalidOutputFolderError, resolve_output_folder

    with pytest.raises(InvalidOutputFolderError):
        resolve_output_folder("/tmp/outside", DataCacheConfig(directory=str(tmp_path / "cache")))
