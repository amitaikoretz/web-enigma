from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ApiDependencies, get_deps
from app.api.schemas.server import ServerInfoResponse

router = APIRouter(prefix="/server", tags=["server"])


@router.get("/info", response_model=ServerInfoResponse)
def get_server_info(deps: ApiDependencies = Depends(get_deps)) -> ServerInfoResponse:
    return ServerInfoResponse(
        backtest_results_dir=str(deps.output_dir),
        platform_settings_path=str(deps.settings_service.path.resolve()),
    )
