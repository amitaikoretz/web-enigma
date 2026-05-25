from __future__ import annotations

import threading
from pathlib import Path

from app.settings.models import PlatformSettings


class PlatformSettingsService:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()

    def load(self) -> PlatformSettings:
        if not self.path.exists():
            return PlatformSettings()
        return PlatformSettings.model_validate_json(self.path.read_text(encoding="utf-8"))

    def save(self, settings: PlatformSettings) -> PlatformSettings:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            temp_path = self.path.with_suffix(".tmp")
            temp_path.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
            temp_path.replace(self.path)
        return settings
