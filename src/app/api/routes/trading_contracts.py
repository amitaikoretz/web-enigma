from __future__ import annotations

from datetime import UTC, datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.contract_mutations import get_contract_mutation_service
from app.contracts import (
    TradingContractActiveQuery,
    TradingContractCreate,
    TradingContractListQuery,
    TradingContractResponse,
    TradingContractUpdate,
    apply_contract_update,
    get_live_contract_or_none,
    load_active_contracts,
    not_deleted_contracts_query,
    to_contract_record,
)
from app.db.models import TradingContract
from app.db.session import get_db_session

router = APIRouter(prefix="/trading-contracts", tags=["trading-contracts"])


@router.post("", response_model=TradingContractResponse, status_code=status.HTTP_201_CREATED)
def create_trading_contract(
    payload: TradingContractCreate,
    session: Session = Depends(get_db_session),
) -> TradingContractResponse:
    record = to_contract_record(payload)
    session.add(record)
    session.commit()
    session.refresh(record)
    return TradingContractResponse.from_model(record)


@router.get("", response_model=list[TradingContractResponse])
def list_trading_contracts(
    symbol: str | None = Query(None),
    strategy: str | None = Query(None),
    session: Session = Depends(get_db_session),
) -> list[TradingContractResponse]:
    try:
        filters = TradingContractListQuery(symbol=symbol, strategy=strategy)
    except ValidationError as exc:
        errors = [error["msg"] for error in exc.errors()]
        raise HTTPException(status_code=422, detail=errors) from exc

    query = not_deleted_contracts_query().order_by(TradingContract.start_datetime.desc())
    if filters.symbol is not None:
        query = query.where(TradingContract.symbol == filters.symbol)
    if filters.strategy is not None:
        query = query.where(TradingContract.strategy == filters.strategy)

    contracts = session.execute(query).scalars().all()
    return [TradingContractResponse.from_model(contract) for contract in contracts]


@router.get("/active", response_model=list[TradingContractResponse])
def get_active_trading_contracts(
    symbol: str | None = Query(None),
    strategy: str | None = Query(None),
    active_at: datetime | None = Query(None),
    session: Session = Depends(get_db_session),
) -> list[TradingContractResponse]:
    try:
        filters = TradingContractActiveQuery(symbol=symbol, strategy=strategy, active_at=active_at)
    except ValidationError as exc:
        errors = [error["msg"] for error in exc.errors()]
        raise HTTPException(status_code=422, detail=errors) from exc

    resolved_active_at = filters.active_at or datetime.now(timezone.utc)
    contracts = load_active_contracts(
        session,
        active_at=resolved_active_at,
        symbol=filters.symbol,
        strategy=filters.strategy,
    )
    return [TradingContractResponse.from_model(contract) for contract in contracts]


@router.patch("/{contract_id}", response_model=TradingContractResponse)
def update_trading_contract(
    contract_id: UUID,
    payload: TradingContractUpdate,
    session: Session = Depends(get_db_session),
) -> TradingContractResponse:
    record = get_live_contract_or_none(session, contract_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trading contract not found")

    if not payload.model_fields_set:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=["No fields provided for update"])

    try:
        apply_contract_update(record, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=[str(exc)]) from exc

    session.commit()
    session.refresh(record)
    get_contract_mutation_service().invalidate_contract(
        session,
        contract_id=record.id,
        revision=int(record.revision),
    )
    return TradingContractResponse.from_model(record)


@router.delete("/{contract_id}", response_model=TradingContractResponse)
def delete_trading_contract(
    contract_id: UUID,
    session: Session = Depends(get_db_session),
) -> TradingContractResponse:
    record = get_live_contract_or_none(session, contract_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trading contract not found")

    record.deleted_at = datetime.now(UTC)
    record.revision = int(record.revision) + 1
    session.commit()
    session.refresh(record)
    get_contract_mutation_service().invalidate_contract(
        session,
        contract_id=record.id,
        revision=int(record.revision),
    )
    return TradingContractResponse.from_model(record)
