from __future__ import annotations

import logging

from app.strategies.auditor_logging import get_strategy_logger, log_auditor_rejection


def test_log_auditor_rejection_writes_to_strategy_logger():
    logger = get_strategy_logger()
    logger.setLevel(logging.INFO)
    records: list[logging.LogRecord] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _CaptureHandler()
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
    try:
        log_auditor_rejection(symbol="AAPL", timestamp="2026-05-06T14:45:00+00:00", reason="weak_close")
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    assert "auditor reject" in records[0].getMessage()
    assert "weak_close" in records[0].getMessage()
