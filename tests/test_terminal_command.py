from __future__ import annotations

from pathlib import Path

from app.cli import main
from app.terminal_command import format_terminal_command


def test_format_terminal_command_quotes():
    assert format_terminal_command(["kalyxctl", "run", "--config", "a b.yaml"]) == "kalyxctl run --config 'a b.yaml'"


def test_cli_writes_terminal_command_file(tmp_path: Path) -> None:
    out = tmp_path / "terminal-command.txt"
    exit_code = main(["--terminal-command-out", str(out), "list-strategies"])
    assert exit_code == 0
    assert out.read_text(encoding="utf-8").strip() == "kalyxctl --terminal-command-out " + str(out) + " list-strategies"
