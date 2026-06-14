from __future__ import annotations

from datetime import date
from pathlib import Path

from app.backtests.models import VectorbtWorkflowRequest
from app.standalone import run_vectorbt_backtest_argo


def test_vectorbt_script_path_is_repo_local() -> None:
    script_path = run_vectorbt_backtest_argo._script_path()
    assert script_path.is_file()
    assert script_path.name == "backtest_risk_gated_ma.py"
    assert "research" not in str(script_path)


def test_build_command_uses_repo_local_script(tmp_path: Path) -> None:
    request = VectorbtWorkflowRequest(
        backtest_id="bt-1",
        dataset_path="/tmp/dataset.parquet",
        dataset_manifest_path="/tmp/dataset.manifest.json",
        risk_model_artifact_path="/tmp/model.json",
        from_date=date(2024, 1, 1),
        max_symbols=3,
        volume_window=21,
        min_volume_ratio=1.5,
        entry_cutoff_minutes=45,
        risk_threshold=0.42,
        exit_style="trailing",
        min_hold_minutes=15.0,
        atr_window=10,
        atr_stop_mult=2.0,
    )

    command = run_vectorbt_backtest_argo._build_command(request, tmp_path)
    assert command[1].endswith("backtest_risk_gated_ma.py")
    assert "--model-path" in command
    assert "/Users/amitaikoretz/code/research" not in " ".join(command)
