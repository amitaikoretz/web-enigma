from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.request import Request
import pandas as pd
import pytest

from app.standalone import datasets_download_argo as module
from app.config.models import AlpacaOptionsDataSource
from app.data import loaders


def test_main_fails_when_alpaca_options_returns_403(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "build_alpaca_data_feed_with_cache",
        lambda *args, **kwargs: (pd.DataFrame({"datetime": [datetime(2026, 6, 1, tzinfo=UTC)], "Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1.0]}), "miss"),
    )

    def raise_403(*args, **kwargs):
        raise RuntimeError("Alpaca options request failed (403): Forbidden")

    monkeypatch.setattr(module, "build_alpaca_options_data_feed_with_cache", raise_403)

    with pytest.raises(RuntimeError, match="Alpaca options request failed \\(403\\): Forbidden"):
        module.main(
            symbol="AAPL",
            provider="alpaca",
            resolution="5m",
            start_date=date(2026, 5, 8).isoformat(),
            end_date=date(2026, 6, 7).isoformat(),
            options_enabled=True,
            options_feed="indicative",
            output_dir=str(tmp_path),
            terminal_command_out=str(tmp_path / "terminal-command.txt"),
            dataset_path_out=str(tmp_path / "dataset-path.txt"),
            manifest_path_out=str(tmp_path / "manifest-path.txt"),
            options_dataset_path_out=str(tmp_path / "options-dataset-path.txt"),
            options_manifest_path_out=str(tmp_path / "options-manifest-path.txt"),
        )


def test_main_writes_blank_options_outputs_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        module,
        "build_alpaca_data_feed_with_cache",
        lambda *args, **kwargs: (pd.DataFrame({"datetime": [datetime(2026, 6, 1, tzinfo=UTC)], "Open": [1.0], "High": [1.0], "Low": [1.0], "Close": [1.0], "Volume": [1.0]}), "miss"),
    )
    monkeypatch.setattr(module, "build_alpaca_options_data_feed_with_cache", lambda *args, **kwargs: pytest.fail("options feed should not be loaded"))

    module.main(
        symbol="AAPL",
        provider="alpaca",
        resolution="5m",
        start_date=date(2026, 5, 8).isoformat(),
        end_date=date(2026, 6, 7).isoformat(),
        options_enabled=False,
        options_feed="indicative",
        output_dir=str(tmp_path),
        terminal_command_out=str(tmp_path / "terminal-command.txt"),
        dataset_path_out=str(tmp_path / "dataset-path.txt"),
        manifest_path_out=str(tmp_path / "manifest-path.txt"),
        options_dataset_path_out=str(tmp_path / "options-dataset-path.txt"),
        options_manifest_path_out=str(tmp_path / "options-manifest-path.txt"),
    )

    assert (tmp_path / "options-dataset-path.txt").read_text(encoding="utf-8") == ""
    assert (tmp_path / "options-manifest-path.txt").read_text(encoding="utf-8") == ""


def test_main_persists_timestamps_in_written_parquet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    timestamps = pd.to_datetime(
        ["2026-06-01T14:30:00Z", "2026-06-01T14:35:00Z"],
        utc=True,
    )
    frame = pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [101.0, 102.0],
            "Low": [99.5, 100.5],
            "Close": [100.5, 101.5],
            "Volume": [1_000, 1_200],
        },
        index=pd.DatetimeIndex(timestamps, name="datetime"),
    )
    options_frame = frame.copy()

    monkeypatch.setattr(module, "build_alpaca_data_feed_with_cache", lambda *args, **kwargs: (frame, "miss"))
    monkeypatch.setattr(
        module,
        "build_alpaca_options_data_feed_with_cache",
        lambda *args, **kwargs: (options_frame, "miss"),
    )

    module.main(
        symbol="AAPL",
        provider="alpaca",
        resolution="5m",
        start_date=date(2026, 5, 8).isoformat(),
        end_date=date(2026, 6, 7).isoformat(),
        options_enabled=True,
        options_feed="indicative",
        output_dir=str(tmp_path),
        terminal_command_out=str(tmp_path / "terminal-command.txt"),
        dataset_path_out=str(tmp_path / "dataset-path.txt"),
        manifest_path_out=str(tmp_path / "manifest-path.txt"),
        options_dataset_path_out=str(tmp_path / "options-dataset-path.txt"),
        options_manifest_path_out=str(tmp_path / "options-manifest-path.txt"),
    )

    dataset = pd.read_parquet(tmp_path / "AAPL-alpaca-5m.parquet")
    options_dataset = pd.read_parquet(tmp_path / "AAPL-alpaca-options-5m.parquet")

    assert "timestamp" in dataset.columns
    assert "timestamp" in options_dataset.columns
    assert dataset["timestamp"].iloc[0] == timestamps[0]
    assert options_dataset["timestamp"].iloc[0] == timestamps[0]


def test_alpaca_options_bars_request_does_not_send_feed_query_param(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    monkeypatch.setattr(loaders, "_fetch_alpaca_option_contract_symbols", lambda *args, **kwargs: ["AAPL240607C00100000"])

    requests: list[Request] = []

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            payload = {
                "bars": [
                    {
                        "t": "2026-06-01T10:00:00Z",
                        "o": 1.0,
                        "h": 1.0,
                        "l": 1.0,
                        "c": 1.0,
                        "v": 1.0,
                    }
                ]
            }
            return json.dumps(payload).encode("utf-8")

    def fake_urlopen(req: Request, timeout: int = 30) -> _Response:
        requests.append(req)
        return _Response()

    monkeypatch.setattr(loaders, "urlopen", fake_urlopen)

    frame = loaders._download_alpaca_options(
        AlpacaOptionsDataSource(type="alpaca-options", symbol="AAPL", interval="5m", feed="indicative"),
        date(2026, 5, 8),
        date(2026, 6, 7),
    )

    assert not frame.empty
    assert len(requests) == 1
    assert "feed=" not in requests[0].full_url
