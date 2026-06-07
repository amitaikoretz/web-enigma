from __future__ import annotations

import json
import logging
from typing import Any


def log_argo_workflow_submission(
    logger: logging.Logger,
    *,
    endpoint_name: str,
    method: str,
    path: str,
    payload: Any,
) -> None:
    payload_json = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    logger.info(
        "argo workflow submission endpoint=%s route=%s payload=%s",
        endpoint_name,
        f"{method.upper()} {path}",
        payload_json,
    )
