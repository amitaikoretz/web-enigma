from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError


def validation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        detail = [error["msg"] for error in exc.errors()]
    else:
        detail = [str(exc)]
    return HTTPException(status_code=422, detail=detail)


def http_error_from_loader_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    if "Alpaca credentials missing" in message:
        return HTTPException(status_code=500, detail=message)
    if "Unsupported Alpaca interval" in message or "No Alpaca data found" in message:
        return HTTPException(status_code=400, detail=message)
    if "Alpaca request failed" in message or "Failed to reach Alpaca data API" in message:
        return HTTPException(status_code=502, detail=message)
    return HTTPException(status_code=500, detail=message)
