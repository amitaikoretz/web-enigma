from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from app.api import create_app


def test_create_app_prefers_pvc_results_dir_when_available(monkeypatch):
    monkeypatch.delenv("BACKTEST_RESULTS_DIR", raising=False)
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)

    pvc_path = Path("/data/backtest-results")
    original_is_dir = Path.is_dir
    original_exists = Path.exists
    original_access = os.access

    def _is_dir(self: Path) -> bool:  # type: ignore[override]
        if self == pvc_path:
            return True
        return original_is_dir(self)

    def _exists(self: Path) -> bool:  # type: ignore[override]
        if self == pvc_path:
            return True
        return original_exists(self)

    def _access(path: Path | str, mode: int) -> bool:  # type: ignore[override]
        if Path(path) == pvc_path:
            return True
        return original_access(path, mode)

    with patch.object(Path, "is_dir", _is_dir), patch.object(Path, "exists", _exists), patch.object(os, "access", _access):
        app = create_app()

    assert app.state.deps.output_dir == pvc_path.resolve()
