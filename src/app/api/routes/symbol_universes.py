from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.universes.argo import SymbolUniverseWorkflowSubmitter
from app.universes.models import (
    SymbolUniverseConstituentsResponse,
    SymbolUniverseCreate,
    SymbolUniverseListItem,
    SymbolUniversePatch,
    SymbolUniverseRefreshRequest,
    SymbolUniverseRefreshResponse,
    UserUniverseCreateRequest,
    UserUniversePatchRequest,
    UserUniverseReplaceSymbolsRequest,
)
from app.universes.service import InvalidUniverseError, SymbolUniverseService


router = APIRouter(prefix="/universes", tags=["symbol-universes"])
service = SymbolUniverseService()
argo_submitter = SymbolUniverseWorkflowSubmitter()


@router.get("", response_model=list[SymbolUniverseListItem])
def list_universes(
    active_only: bool = Query(True),
    session: Session = Depends(get_db_session),
) -> list[dict]:
    return service.list_universes(session, active_only=active_only)


@router.post("", response_model=SymbolUniverseListItem, status_code=status.HTTP_201_CREATED)
def create_universe(
    payload: SymbolUniverseCreate,
    session: Session = Depends(get_db_session),
) -> dict:
    record = service.create_universe(session, payload=payload.model_dump())
    items = service.list_universes(session, active_only=False)
    for item in items:
        if item["key"] == record.key:
            return item
    return {
        "key": record.key,
        "name": record.name,
        "description": record.description,
        "provider": record.provider,
        "provider_ref": record.provider_ref or {},
        "is_active": bool(record.is_active),
        "latest_refresh_status": None,
        "latest_refresh_started_at": None,
        "latest_refresh_as_of": None,
    }


@router.patch("/{key}", response_model=SymbolUniverseListItem)
def patch_universe(
    key: str,
    payload: SymbolUniversePatch,
    session: Session = Depends(get_db_session),
) -> dict:
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail=["No fields provided for update"])

    try:
        service.patch_universe(session, key=key, patch=payload.model_dump(exclude_unset=True))
    except InvalidUniverseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    items = service.list_universes(session, active_only=False)
    for item in items:
        if item["key"] == key.strip().lower():
            return item
    raise HTTPException(status_code=404, detail="Universe not found")


@router.get("/{key}/constituents", response_model=SymbolUniverseConstituentsResponse)
def get_universe_constituents(
    key: str,
    as_of: date = Query(...),
    session: Session = Depends(get_db_session),
) -> SymbolUniverseConstituentsResponse:
    record = service.get_universe(session, key=key)
    if record is None:
        raise HTTPException(status_code=404, detail="Universe not found")
    symbols = service.constituents_as_of(session, universe=record, as_of=as_of)
    return SymbolUniverseConstituentsResponse(key=record.key, as_of=as_of, symbols=symbols)


@router.post("/{key}/refresh", response_model=SymbolUniverseRefreshResponse)
def submit_universe_refresh(
    key: str,
    payload: SymbolUniverseRefreshRequest,
    session: Session = Depends(get_db_session),
) -> SymbolUniverseRefreshResponse:
    record = service.get_universe(session, key=key)
    if record is None:
        raise HTTPException(status_code=404, detail="Universe not found")
    resolved_as_of = payload.as_of or date.today()
    try:
        workflow_name, namespace = argo_submitter.submit_refresh(universe_key=record.key, as_of=resolved_as_of.isoformat())
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SymbolUniverseRefreshResponse(workflow_name=workflow_name, namespace=namespace)


@router.post("/refresh", response_model=SymbolUniverseRefreshResponse)
def submit_bulk_universe_refresh(
    payload: SymbolUniverseRefreshRequest,
) -> SymbolUniverseRefreshResponse:
    resolved_as_of = payload.as_of or date.today()
    try:
        workflow_name, namespace = argo_submitter.submit_refresh(universe_key=None, as_of=resolved_as_of.isoformat())
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SymbolUniverseRefreshResponse(workflow_name=workflow_name, namespace=namespace)


@router.post("/sync-registry", response_model=SymbolUniverseRefreshResponse)
def submit_universe_registry_sync() -> SymbolUniverseRefreshResponse:
    try:
        workflow_name, namespace = argo_submitter.submit_sync_registry()
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return SymbolUniverseRefreshResponse(workflow_name=workflow_name, namespace=namespace)


@router.post("/user", response_model=SymbolUniverseListItem, status_code=status.HTTP_201_CREATED)
def create_user_universe(
    payload: UserUniverseCreateRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    record = service.create_user_universe(
        session,
        name=payload.name,
        symbols=payload.symbols,
        description=payload.description,
        is_active=payload.is_active,
        created_on=date.today(),
    )
    items = service.list_universes(session, active_only=False)
    for item in items:
        if item["key"] == record.key:
            return item
    raise HTTPException(status_code=500, detail="Failed to return created universe")


@router.patch("/user/{key}", response_model=SymbolUniverseListItem)
def patch_user_universe(
    key: str,
    payload: UserUniversePatchRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail=["No fields provided for update"])
    try:
        service.patch_user_universe(
            session,
            key=key,
            name=payload.name,
            description=payload.description,
            is_active=payload.is_active,
        )
    except InvalidUniverseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    items = service.list_universes(session, active_only=False)
    for item in items:
        if item["key"] == key.strip().lower():
            return item
    raise HTTPException(status_code=404, detail="Universe not found")


@router.put("/user/{key}/symbols", response_model=dict)
def replace_user_universe_symbols(
    key: str,
    payload: UserUniverseReplaceSymbolsRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    record = service.get_universe(session, key=key)
    if record is None or record.kind != "user":
        raise HTTPException(status_code=404, detail="User universe not found")
    effective_on = payload.effective_on or date.today()
    stats = service.replace_user_universe_symbols(session, universe=record, symbols=payload.symbols, effective_on=effective_on)
    return {"key": record.key, "effective_on": effective_on.isoformat(), **stats}


@router.delete("/user/{key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user_universe(
    key: str,
    session: Session = Depends(get_db_session),
) -> None:
    try:
        service.delete_user_universe(session, key=key)
    except InvalidUniverseError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return None
