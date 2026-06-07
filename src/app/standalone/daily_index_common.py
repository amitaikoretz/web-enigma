from __future__ import annotations

import shlex
import sys
from pathlib import Path
from typing import Any


def write_text(path: str | None, text: str) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def terminal_command(argv: list[str] | None = None) -> str:
    args = argv if argv is not None else sys.argv
    return " ".join(shlex.quote(arg) for arg in args)


def json_default(value: Any) -> Any:
    if hasattr(value, "item"):
        return value.item()
    return str(value)

