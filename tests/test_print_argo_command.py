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
    lines = [line for line in captured.out.splitlines() if line.strip()]
    assert lines[0].startswith("ts=")
    assert "level=info" in lines[0]
    assert "script=print_argo_command" in lines[0]
    assert "event=terminal-command" in lines[0]
    assert "python -m app.standalone.print_argo_command --flag" in lines[0]
    assert any("event=launch-command" in line and "python -m app.standalone.example --flag value" in line for line in lines)
