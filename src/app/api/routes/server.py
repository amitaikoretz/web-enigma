from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import ApiDependencies, get_deps
from app.api.schemas.server import ServerInfoResponse

router = APIRouter(prefix="/server", tags=["server"])


@router.get("/info", response_model=ServerInfoResponse)
def get_server_info(deps: ApiDependencies = Depends(get_deps)) -> ServerInfoResponse:
    settings = deps.settings_service.load()
    argo_enabled = deps.backtest_jobs.argo_submitter.is_configured
    return ServerInfoResponse(
        backtest_results_dir=str(deps.output_dir),
        platform_settings_path=str(deps.settings_service.path.resolve()),
        argo_workflows_enabled=argo_enabled,
        backtest_execution_backend=settings.platform_behavior.backtest_execution_backend,
    )
