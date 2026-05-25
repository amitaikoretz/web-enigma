from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ApiDependencies, get_deps
from app.settings import PlatformSettings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=PlatformSettings)
def get_settings(deps: ApiDependencies = Depends(get_deps)) -> PlatformSettings:
    return deps.settings_service.load()


@router.put("", response_model=PlatformSettings)
def put_settings(
    payload: PlatformSettings,
    deps: ApiDependencies = Depends(get_deps),
) -> PlatformSettings:
    return deps.settings_service.save(payload)
