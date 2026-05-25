from __future__ import annotations

from datetime import datetime
from typing import Protocol

from app.live.models import (
    BrokerFillSnapshot,
    BrokerHealthStatus,
    BrokerOrderAck,
    BrokerOrderSnapshot,
    BrokerPositionSnapshot,
    SubmitOrderRequest,
)


class BrokerAdapter(Protocol):
    broker_name: str

    def submit_order(self, request: SubmitOrderRequest) -> BrokerOrderAck: ...

    def list_open_orders(self, symbol: str) -> list[BrokerOrderSnapshot]: ...

    def get_position(self, symbol: str) -> BrokerPositionSnapshot | None: ...

    def list_recent_fills(self, symbol: str, since: datetime | None = None) -> list[BrokerFillSnapshot]: ...

    def cancel_order(self, broker_order_id: str) -> None: ...

    def healthcheck(self) -> BrokerHealthStatus: ...


class AlpacaPaperBrokerAdapter:
    broker_name = "alpaca"

    def submit_order(self, request: SubmitOrderRequest) -> BrokerOrderAck:
        raise NotImplementedError("Live worker order submission is not implemented in this runtime skeleton")

    def list_open_orders(self, symbol: str) -> list[BrokerOrderSnapshot]:
        return []

    def get_position(self, symbol: str) -> BrokerPositionSnapshot | None:
        return None

    def list_recent_fills(self, symbol: str, since: datetime | None = None) -> list[BrokerFillSnapshot]:
        return []

    def cancel_order(self, broker_order_id: str) -> None:
        raise NotImplementedError("Broker order cancellation is not implemented in this runtime skeleton")

    def healthcheck(self) -> BrokerHealthStatus:
        return BrokerHealthStatus(ok=True, detail="alpaca paper adapter stub")
