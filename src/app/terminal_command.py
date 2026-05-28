from __future__ import annotations

import shlex


def format_terminal_command(argv: list[str]) -> str:
    return shlex.join(argv)

