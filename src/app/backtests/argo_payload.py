from __future__ import annotations

import json
from typing import Any, Literal


def build_argo_launch_payload(
    *,
    config_path: str | None = None,
    config_text: str | None = None,
    split_by: str = "",
    backtest_id: str = "",
    format: Literal["yaml", "json"] = "yaml",
) -> dict[str, Any]:
    has_path = bool(config_path and config_path.strip())
    has_text = bool(config_text and config_text.strip())
    if has_path == has_text:
        raise ValueError("Provide exactly one of config_path or config_text")

    payload: dict[str, Any] = {}
    if has_text:
        payload["format"] = format
        payload["config_text"] = config_text
    else:
        payload["config_path"] = config_path

    if split_by.strip():
        payload["split_by"] = split_by.strip()
    if backtest_id.strip():
        payload["backtest_id"] = backtest_id.strip()
    return payload


def format_argo_launch_curl(api_base_url: str, payload: dict[str, Any]) -> str:
    base = api_base_url.rstrip("/")
    body = json.dumps(payload, ensure_ascii=False)
    return (
        f"curl -sS -X POST '{base}/backtests/argo' \\\n"
        f"  -H 'Content-Type: application/json' \\\n"
        f"  -d '{body}'"
    )
