from __future__ import annotations

import logging

STRATEGY_LOGGER_NAME = "app.strategy"


def get_strategy_logger() -> logging.Logger:
    return logging.getLogger(STRATEGY_LOGGER_NAME)


def configure_strategy_logging(*, also_console: bool = True) -> logging.Logger:
    logger = get_strategy_logger()
    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    if also_console:
        handler = logging.StreamHandler()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_auditor_rejection(*, symbol: str | None, timestamp: str, reason: str | None) -> None:
    if not reason:
        return
    get_strategy_logger().info(
        "auditor reject symbol=%s time=%s reason=%s",
        symbol or "-",
        timestamp,
        reason,
    )
