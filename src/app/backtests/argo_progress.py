from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

ARGO_PROGRESS_TOTAL = 100


def resolve_progress_file(explicit: str | None = None) -> Path | None:
    path = explicit or os.environ.get("ARGO_PROGRESS_FILE")
    if not path:
        return None
    return Path(path)


def pct_from_run_index(idx: int, total: int) -> int:
    if total <= 0:
        return ARGO_PROGRESS_TOTAL
    return round(idx * ARGO_PROGRESS_TOTAL / total)


def pct_from_run_and_bar(run_idx: int, total_runs: int, bar_idx: int, bar_total: int) -> int:
    if total_runs <= 0:
        return ARGO_PROGRESS_TOTAL
    if bar_total <= 0:
        return pct_from_run_index(run_idx, total_runs)
    completed = (run_idx - 1) + (bar_idx / bar_total)
    return round(min(1.0, completed / total_runs) * ARGO_PROGRESS_TOTAL)


def write_argo_progress(path: Path, completed: int, *, total: int = ARGO_PROGRESS_TOTAL) -> None:
    clamped = max(0, min(total, completed))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{clamped}/{total}\n", encoding="utf-8")


@dataclass
class ThrottledProgressWriter:
    path: Path
    min_interval_sec: float = 2.0
    _last_pct: int | None = field(default=None, init=False, repr=False)
    _last_write_at: float = field(default=0.0, init=False, repr=False)

    def write(self, pct: int) -> None:
        now = time.monotonic()
        if (
            self._last_pct == pct
            and self._last_write_at > 0.0
            and (now - self._last_write_at) < self.min_interval_sec
        ):
            return
        write_argo_progress(self.path, pct)
        self._last_pct = pct
        self._last_write_at = now

    def write_immediate(self, pct: int) -> None:
        write_argo_progress(self.path, pct)
        self._last_pct = pct
        self._last_write_at = time.monotonic()


def parse_argo_progress(value: str) -> tuple[int, int] | None:
    normalized = value.strip()
    if not normalized:
        return None
    line = normalized.splitlines()[-1].strip()
    if "/" not in line:
        return None
    left, right = line.split("/", 1)
    try:
        completed = int(left.strip())
        total = int(right.strip())
    except ValueError:
        return None
    if completed < 0 or total < 0:
        return None
    return completed, total


def progress_fraction(completed: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return min(1.0, max(0.0, completed / total))
