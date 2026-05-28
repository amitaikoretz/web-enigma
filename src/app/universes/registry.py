from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class UniverseSpec:
    key: str
    name: str
    description: str | None
    provider: str


UNIVERSE_REGISTRY: dict[str, UniverseSpec] = {
    "sp500": UniverseSpec(
        key="sp500",
        name="S&P 500",
        description="Large-cap US equities (S&P 500 constituents).",
        provider="wikipedia",
    ),
    "nasdaq100": UniverseSpec(
        key="nasdaq100",
        name="NASDAQ 100",
        description="NASDAQ 100 constituents.",
        provider="wikipedia",
    ),
    "dow30": UniverseSpec(
        key="dow30",
        name="Dow 30",
        description="Dow Jones Industrial Average constituents.",
        provider="wikipedia",
    ),
}
