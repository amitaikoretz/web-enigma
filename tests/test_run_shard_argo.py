from __future__ import annotations

from pathlib import Path

import pytest
import typer

from app.standalone import run_shard_argo


def test_run_shard_writes_output_path_even_when_shard_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out = tmp_path / "shard-output-path.txt"
    config_path = tmp_path / "config.yaml"
    output_path = tmp_path / "shards" / "unknown_buy_and_hold.json"

    config_path.write_text("runs: []\n", encoding="utf-8")
    monkeypatch.setattr(run_shard_argo, "_cmd_run", lambda **kwargs: 20)
    monkeypatch.setattr(run_shard_argo.sys, "argv", ["kalyxctl", "run-shard"])

    with pytest.raises(typer.Exit):
        run_shard_argo.main(
            shard_id="unknown_buy_and_hold",
            config_path=str(config_path),
            output_path=str(output_path),
            cache_dir=str(tmp_path / "cache"),
            shard_output_path_out=str(out),
            terminal_command_out=str(tmp_path / "terminal-command.txt"),
        )

    assert out.read_text(encoding="utf-8") == str(output_path)
