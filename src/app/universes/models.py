from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator


def _normalize_key(value: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise ValueError("key must not be empty")
    if any(ch.isspace() for ch in normalized):
        raise ValueError("key must not contain spaces")
    return normalized


class SymbolUniverseCreate(BaseModel):
    key: str
    name: str
    description: str | None = None
    provider: str
    provider_ref: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        return _normalize_key(value)

    @field_validator("name", "provider")
    @classmethod
    def validate_required_string(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("provider")
    @classmethod
    def reject_deprecated_provider(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized == "fmp":
            raise ValueError("provider 'fmp' is deprecated; use 'wikipedia'")
        return value


class SymbolUniversePatch(BaseModel):
    name: str | None = None
    description: str | None = None
    provider: str | None = None
    provider_ref: dict[str, Any] | None = None
    is_active: bool | None = None

    @field_validator("name", "provider")
    @classmethod
    def validate_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be empty")
        return normalized

    @field_validator("provider")
    @classmethod
    def reject_deprecated_provider(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized == "fmp":
            raise ValueError("provider 'fmp' is deprecated; use 'wikipedia'")
        return value


class SymbolUniverseListItem(BaseModel):
    key: str
    kind: str | None = None
    name: str
    description: str | None
    provider: str | None
    provider_ref: dict[str, Any]
    is_active: bool
    latest_refresh_status: str | None = None
    latest_refresh_started_at: str | None = None
    latest_refresh_as_of: str | None = None


class SymbolUniverseConstituentsResponse(BaseModel):
    key: str
    as_of: date
    symbols: list[str]


class SymbolUniverseRefreshRequest(BaseModel):
    as_of: date | None = None


class SymbolUniverseRefreshResponse(BaseModel):
    workflow_name: str
    namespace: str


class UserUniverseCreateRequest(BaseModel):
    name: str
    description: str | None = None
    symbols: list[str] = Field(default_factory=list)
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized


class UserUniversePatchRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be empty")
        return normalized


class UserUniverseReplaceSymbolsRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list)
    effective_on: date | None = None
