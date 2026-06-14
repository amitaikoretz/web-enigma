from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from app.api import create_app


def test_create_app_prefers_pvc_results_dir_when_available(monkeypatch):
    monkeypatch.delenv("BACKTEST_RESULTS_DIR", raising=False)
    monkeypatch.delenv("BACKTEST_CACHE_DIR", raising=False)

    pvc_path = Path("/data/backtest-results")
    original_mkdir = Path.mkdir
    original_write_text = Path.write_text
    original_unlink = Path.unlink

    def _mkdir(self: Path, *args, **kwargs) -> None:  # type: ignore[override]
        if self == pvc_path:
            return None
        return original_mkdir(self, *args, **kwargs)

    def _write_text(self: Path, data: str, *args, **kwargs) -> int:  # type: ignore[override]
        if self.parent == pvc_path and self.name.startswith(".write-probe-"):
            return len(data)
        return original_write_text(self, data, *args, **kwargs)

    def _unlink(self: Path, *args, **kwargs) -> None:  # type: ignore[override]
        if self.parent == pvc_path and self.name.startswith(".write-probe-"):
            return None
        return original_unlink(self, *args, **kwargs)

    with (
        patch.object(Path, "mkdir", _mkdir),
        patch.object(Path, "write_text", _write_text),
        patch.object(Path, "unlink", _unlink),
    ):
        app = create_app()

    assert app.state.deps.output_dir == pvc_path.resolve()
