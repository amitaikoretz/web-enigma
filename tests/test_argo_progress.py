from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.backtests.argo_progress import (
    ThrottledProgressWriter,
    pct_from_run_and_bar,
    pct_from_run_index,
    resolve_progress_file,
    write_argo_progress,
)
from app.cli import _cmd_run


def test_pct_from_run_index_zero_total() -> None:
    assert pct_from_run_index(0, 0) == 100
    assert pct_from_run_index(5, 0) == 100


def test_pct_from_run_index_single_run() -> None:
    assert pct_from_run_index(1, 1) == 100


def test_pct_from_run_index_multiple_runs() -> None:
    assert pct_from_run_index(1, 3) == 33
    assert pct_from_run_index(2, 3) == 67
    assert pct_from_run_index(3, 3) == 100


def test_pct_from_run_and_bar_mid_run() -> None:
    assert pct_from_run_and_bar(2, 4, 50, 100) == 38
    assert pct_from_run_and_bar(1, 1, 10, 20) == 50
    assert pct_from_run_and_bar(0, 0, 5, 10) == 100


def test_throttled_progress_writer_skips_duplicate_within_interval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    progress_path = tmp_path / "progress"
    writer = ThrottledProgressWriter(progress_path, min_interval_sec=2.0)
    times = iter([1000.0, 1000.5, 1002.5])

    monkeypatch.setattr("app.backtests.argo_progress.time.monotonic", lambda: next(times))

    writer.write(10)
    writer.write(10)
    writer.write(20)

    assert progress_path.read_text(encoding="utf-8") == "20/100\n"


def test_throttled_progress_writer_write_immediate_bypasses_throttle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    progress_path = tmp_path / "progress"
    writer = ThrottledProgressWriter(progress_path, min_interval_sec=2.0)
    times = iter([1000.0, 1000.1, 1000.2])

    monkeypatch.setattr("app.backtests.argo_progress.time.monotonic", lambda: next(times))

    writer.write_immediate(25)
    writer.write_immediate(50)

    assert progress_path.read_text(encoding="utf-8") == "50/100\n"


def test_write_argo_progress_clamps_and_formats(tmp_path: Path) -> None:
    progress_path = tmp_path / "nested" / "progress"
    write_argo_progress(progress_path, 150)
    assert progress_path.read_text(encoding="utf-8") == "100/100\n"

    write_argo_progress(progress_path, -5)
    assert progress_path.read_text(encoding="utf-8") == "0/100\n"


def test_resolve_progress_file_prefers_explicit_over_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    env_path = tmp_path / "env-progress"
    explicit_path = tmp_path / "explicit-progress"
    monkeypatch.setenv("ARGO_PROGRESS_FILE", str(env_path))

    assert resolve_progress_file(str(explicit_path)) == explicit_path
    assert resolve_progress_file() == env_path


def test_resolve_progress_file_returns_none_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARGO_PROGRESS_FILE", raising=False)
    assert resolve_progress_file() is None


def test_cmd_run_writes_progress_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_payload = {
        "runs": [
            {
                "run_id": "run_a",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
            },
            {
                "run_id": "run_b",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
            },
        ]
    }
    cfg_path = tmp_path / "config.yaml"
    out_path = tmp_path / "result.json"
    progress_path = tmp_path / "progress"
    cfg_path.write_text(yaml.safe_dump(config_payload), encoding="utf-8")

    snapshots: list[str] = []
    original_write = write_argo_progress

    def capture_write(path: Path, completed: int, *, total: int = 100) -> None:
        original_write(path, completed, total=total)
        snapshots.append(path.read_text(encoding="utf-8").strip())

    monkeypatch.setattr("app.backtests.argo_progress.write_argo_progress", capture_write)

    code = _cmd_run(
        str(cfg_path),
        str(out_path),
        cache_dir=None,
        cache_refresh=False,
        no_cache=True,
        progress_file=str(progress_path),
    )

    assert code == 0
    assert snapshots[0] == "0/100"
    assert snapshots[-1] == "100/100"
    assert len(set(snapshots)) > 3
    mid_run_values = {int(value.split("/")[0]) for value in snapshots}
    assert any(0 < value < 50 for value in mid_run_values)
    assert any(50 < value < 100 for value in mid_run_values)
    assert progress_path.read_text(encoding="utf-8") == "100/100\n"


def test_cmd_run_does_not_write_progress_without_config(tmp_path: Path) -> None:
    config_payload = {
        "runs": [
            {
                "run_id": "run_a",
                "start_date": "2024-01-01",
                "end_date": "2024-01-19",
                "data": {"type": "csv", "path": "examples/data/sample_daily.csv"},
                "strategy": "buy_and_hold",
                "strategy_params": {"stake": 1},
            }
        ]
    }
    cfg_path = tmp_path / "config.yaml"
    out_path = tmp_path / "result.json"
    progress_path = tmp_path / "progress"
    cfg_path.write_text(yaml.safe_dump(config_payload), encoding="utf-8")

    code = _cmd_run(
        str(cfg_path),
        str(out_path),
        cache_dir=None,
        cache_refresh=False,
        no_cache=True,
    )

    assert code == 0
    assert not progress_path.exists()
