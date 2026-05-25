from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

DEFAULT_LOG_DIR = Path("logs")


def build_timestamped_log_file(log_dir: Path = DEFAULT_LOG_DIR, now: datetime | None = None) -> Path:
    timestamp = (now or datetime.now()).strftime("%Y%m%dT%H%M%S")
    return log_dir / f"api-{timestamp}.log"

_API_LOGGER_NAME = "app.api"
_UVICORN_LOGGER_NAMES = ("uvicorn", "uvicorn.access", "uvicorn.error")
_CONFIGURED_LOG_FILE: Path | None = None


def configure_api_logging(
    log_file: Path | None,
    *,
    also_console: bool = True,
    force: bool = False,
) -> logging.Logger:
    global _CONFIGURED_LOG_FILE

    logger = logging.getLogger(_API_LOGGER_NAME)
    resolved_log_file = log_file.resolve() if log_file is not None else None
    if not force and resolved_log_file is not None and resolved_log_file == _CONFIGURED_LOG_FILE:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handlers: list[logging.Handler] = []
    if resolved_log_file is not None:
        resolved_log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(resolved_log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    if also_console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    for name in (_API_LOGGER_NAME, *_UVICORN_LOGGER_NAMES):
        target = logging.getLogger(name)
        target.handlers.clear()
        for handler in handlers:
            target.addHandler(handler)
        target.setLevel(logging.INFO)
        target.propagate = False

    _CONFIGURED_LOG_FILE = resolved_log_file
    return logger
