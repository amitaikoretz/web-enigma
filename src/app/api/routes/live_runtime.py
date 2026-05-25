from __future__ import annotations

from datetime import datetime

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.api.helpers.live_runtime import build_runtime_state, list_runtime_events
from app.api.live_runtime_deps import LiveRuntimeStores, get_live_runtime_stores
from app.api.schemas.live_runtime import LiveRuntimeEventsQuery, LiveRuntimeResponse
from app.db.session import get_db_session

router = APIRouter(prefix="/live/runtime", tags=["live-runtime"])


@router.get("", response_model=LiveRuntimeResponse)
def get_live_runtime(
    limit: int = Query(100, ge=1, le=500),
    worker_id: str | None = Query(None),
    event_type: str | None = Query(None),
    symbol_key: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    session: Session = Depends(get_db_session),
    stores: LiveRuntimeStores = Depends(get_live_runtime_stores),
) -> LiveRuntimeResponse:
    try:
        events_query = LiveRuntimeEventsQuery(
            limit=limit,
            worker_id=worker_id,
            event_type=event_type,
            symbol_key=symbol_key,
            since=since,
            until=until,
        )
    except ValidationError as exc:
        errors = [error["msg"] for error in exc.errors()]
        raise HTTPException(status_code=422, detail=errors) from exc

    try:
        runtime_state = build_runtime_state(
            assignment_store=stores.assignment_store,
            lease_store=stores.lease_store,
            control_flag_store=stores.control_flag_store,
        )
    except redis.RedisError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Redis is unavailable",
        ) from exc

    events = list_runtime_events(session, events_query)
    return LiveRuntimeResponse(state=runtime_state, events=events)
