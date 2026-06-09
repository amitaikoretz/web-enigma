from __future__ import annotations

import shlex
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO


def _stringify(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _quote(value: Any) -> str:
    return shlex.quote(_stringify(value))


def current_script_name(*, default: str | None = None) -> str:
    if default:
        return default
    return Path(sys.argv[0]).stem or "script"


def format_structured_log(
    *,
    level: str,
    event: str,
    msg: str,
    script: str | None = None,
    ts: str | None = None,
    **fields: Any,
) -> str:
    timestamp = ts or datetime.now(UTC).isoformat(timespec="seconds")
    parts = [
        f"ts={_quote(timestamp)}",
        f"level={_quote(level)}",
        f"script={_quote(script or current_script_name())}",
        f"event={_quote(event)}",
        f"msg={_quote(msg)}",
    ]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={_quote(value)}")
    return " ".join(parts)


def emit_structured_log(
    *,
    level: str,
    event: str,
    msg: str,
    script: str | None = None,
    stream: TextIO | None = None,
    ts: str | None = None,
    **fields: Any,
) -> None:
    target = stream or sys.stdout
    print(
        format_structured_log(level=level, event=event, msg=msg, script=script, ts=ts, **fields),
        file=target,
        flush=True,
    )


def emit_info(event: str, msg: str, *, script: str | None = None, stream: TextIO | None = None, **fields: Any) -> None:
    emit_structured_log(level="info", event=event, msg=msg, script=script, stream=stream, **fields)


def emit_warning(
    event: str,
    msg: str,
    *,
    script: str | None = None,
    stream: TextIO | None = None,
    **fields: Any,
) -> None:
    emit_structured_log(level="warning", event=event, msg=msg, script=script, stream=stream, **fields)


def emit_error(event: str, msg: str, *, script: str | None = None, stream: TextIO | None = None, **fields: Any) -> None:
    emit_structured_log(level="error", event=event, msg=msg, script=script, stream=stream, **fields)


def emit_terminal_command(
    argv: list[str],
    *,
    terminal_command_out: str | None = None,
    script: str | None = None,
    event: str = "terminal-command",
) -> str:
    command = " ".join(shlex.quote(arg) for arg in argv)
    emit_info(event, command, script=script)
    if terminal_command_out:
        target = Path(terminal_command_out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"{command}\n", encoding="utf-8")
    return command
