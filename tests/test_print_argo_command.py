from __future__ import annotations

from pathlib import Path

from app.standalone import print_argo_command as module


def test_print_argo_command_writes_terminal_command(tmp_path: Path, capsys, monkeypatch) -> None:
    terminal_command_out = tmp_path / "terminal-command.txt"

    monkeypatch.setattr(module.sys, "argv", ["python", "-m", "app.standalone.print_argo_command", "--flag"])
    module.main(
        command_line="python -m app.standalone.example --flag value",
        terminal_command_out=str(terminal_command_out),
    )

    assert terminal_command_out.read_text(encoding="utf-8").strip() == "python -m app.standalone.print_argo_command --flag"
    captured = capsys.readouterr()
    assert "python -m app.standalone.example --flag value" in captured.out
