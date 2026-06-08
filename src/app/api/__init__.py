from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import FastAPI

__all__ = ["create_app", "app"]


def create_app(*args: Any, **kwargs: Any):
    from app.api.factory import create_app as _create_app

    return _create_app(*args, **kwargs)


def __getattr__(name: str) -> Any:
    if name == "app":
        value = create_app()
        globals()[name] = value
        return value
    if name == "create_app":
        return create_app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
