from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError


def format_exception_detail(exc: Exception) -> str:
    return str(exc)


def register_exception_handlers(app: FastAPI, logger: logging.Logger) -> None:
    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error(
                "%s %s -> %d: %s",
                request.method,
                request.url.path,
                exc.status_code,
                exc.detail,
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        detail = format_exception_detail(exc)
        logger.exception("%s %s failed: %s", request.method, request.url.path, detail)
        return JSONResponse(status_code=500, content={"detail": detail})


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
