from __future__ import annotations

from datetime import datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.config.models import SessionConfig
from app.live.models import SessionPhase


class SessionCalendar(Protocol):
    def get_phase(self, now: datetime) -> SessionPhase: ...

    def next_transition(self, now: datetime) -> datetime | None: ...


class WallClockSessionCalendar:
    def __init__(
        self,
        *,
        config: SessionConfig,
        market_open: time = time(9, 30),
        market_close: time = time(16, 0),
    ) -> None:
        self.config = config
        self.market_open = market_open
        self.market_close = market_close
        self.zone = ZoneInfo(config.timezone)

    def get_phase(self, now: datetime) -> SessionPhase:
        current = now.astimezone(self.zone)
        open_dt = current.replace(hour=self.market_open.hour, minute=self.market_open.minute, second=0, microsecond=0)
        close_dt = current.replace(hour=self.market_close.hour, minute=self.market_close.minute, second=0, microsecond=0)
        pre_open_dt = open_dt - timedelta(minutes=self.config.pre_open_warmup_minutes)
        drain_end = close_dt + timedelta(minutes=self.config.drain_timeout_minutes)

        if pre_open_dt <= current < open_dt:
            return SessionPhase.PRE_OPEN
        if open_dt <= current < close_dt:
            return SessionPhase.OPEN
        if close_dt <= current < drain_end:
            return SessionPhase.DRAINING
        return SessionPhase.CLOSED

    def next_transition(self, now: datetime) -> datetime | None:
        current = now.astimezone(self.zone)
        open_dt = current.replace(hour=self.market_open.hour, minute=self.market_open.minute, second=0, microsecond=0)
        close_dt = current.replace(hour=self.market_close.hour, minute=self.market_close.minute, second=0, microsecond=0)
        pre_open_dt = open_dt - timedelta(minutes=self.config.pre_open_warmup_minutes)
        drain_end = close_dt + timedelta(minutes=self.config.drain_timeout_minutes)
        for candidate in (pre_open_dt, open_dt, close_dt, drain_end):
            if candidate > current:
                return candidate
        return pre_open_dt + timedelta(days=1)


class FixedSessionCalendar:
    def __init__(self, phase: SessionPhase) -> None:
        self.phase = phase

    def get_phase(self, now: datetime) -> SessionPhase:
        return self.phase

    def next_transition(self, now: datetime) -> datetime | None:
        return None
