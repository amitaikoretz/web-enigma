from __future__ import annotations

from typing import Protocol

from app.live.models import MarketDataHealthStatus, MarketEvent
from app.strategies.core import Bar


class MarketDataAdapter(Protocol):
    source_name: str

    def warmup_bars(self, symbol: str, interval: str, limit: int) -> list[Bar]: ...

    def subscribe(self, symbol: str, interval: str) -> None: ...

    def unsubscribe(self, symbol: str, interval: str) -> None: ...

    def poll_events(self) -> list[MarketEvent]: ...

    def healthcheck(self) -> MarketDataHealthStatus: ...


class NoopMarketDataAdapter:
    source_name = "noop"

    def warmup_bars(self, symbol: str, interval: str, limit: int) -> list[Bar]:
        return []

    def subscribe(self, symbol: str, interval: str) -> None:
        return None

    def unsubscribe(self, symbol: str, interval: str) -> None:
        return None

    def poll_events(self) -> list[MarketEvent]:
        return []

    def healthcheck(self) -> MarketDataHealthStatus:
        return MarketDataHealthStatus(ok=True, detail="noop market data adapter")
