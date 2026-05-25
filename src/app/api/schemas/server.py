from __future__ import annotations

from pydantic import BaseModel


class ServerInfoResponse(BaseModel):
    backtest_results_dir: str
    platform_settings_path: str
