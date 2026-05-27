from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.strategies.core import StrategyDecision

CandidateSide = Literal["LONG", "SHORT"]
CandidateEntryType = Literal["CLOSE", "NEXT_OPEN", "MARKET", "LIMIT", "MID"]


@dataclass(frozen=True)
class EntryIntent:
    entry_price: float
    planned_stop_pct: float
    planned_target_pct: float | None
    planned_horizon_bars: int
    signal_score: float | None = None
    signal_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class CandidateEvent(BaseModel):
    candidate_id: str
    strategy_id: str
    symbol: str
    timestamp: str
    side: CandidateSide = "LONG"
    entry_price: float
    entry_type: CandidateEntryType = "CLOSE"
    planned_stop_pct: float
    planned_target_pct: float | None = None
    planned_horizon_bars: int
    signal_score: float | None = None
    signal_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    was_traded: bool = False
    reject_reason: str | None = None


def make_candidate_id(*, strategy_id: str, symbol: str, timestamp: str, side: str) -> str:
    raw = f"{strategy_id}|{symbol}|{timestamp}|{side}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def finalize_candidate(
    decision: StrategyDecision,
    *,
    strategy_id: str,
    symbol: str,
    timestamp: str,
    entry_type: CandidateEntryType,
    side: CandidateSide = "LONG",
) -> CandidateEvent | None:
    intent = decision.entry_intent
    if intent is None:
        return None
    return CandidateEvent(
        candidate_id=make_candidate_id(
            strategy_id=strategy_id,
            symbol=symbol,
            timestamp=timestamp,
            side=side,
        ),
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp=timestamp,
        side=side,
        entry_price=intent.entry_price,
        entry_type=entry_type,
        planned_stop_pct=intent.planned_stop_pct,
        planned_target_pct=intent.planned_target_pct,
        planned_horizon_bars=intent.planned_horizon_bars,
        signal_score=intent.signal_score,
        signal_reason=intent.signal_reason,
        metadata=dict(intent.metadata),
        was_traded=decision.action == "buy",
        reject_reason=None if decision.action == "buy" else decision.reason,
    )


def record_candidate(
    log: list[CandidateEvent],
    decision: StrategyDecision,
    *,
    enabled: bool,
    strategy_id: str,
    symbol: str,
    timestamp: str,
    entry_type: CandidateEntryType,
    side: CandidateSide = "LONG",
) -> CandidateEvent | None:
    if not enabled:
        return None
    event = finalize_candidate(
        decision,
        strategy_id=strategy_id,
        symbol=symbol,
        timestamp=timestamp,
        entry_type=entry_type,
        side=side,
    )
    if event is not None:
        log.append(event)
    return event
