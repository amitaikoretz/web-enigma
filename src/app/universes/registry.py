from __future__ import annotations

from dataclasses import dataclass

from app.universes.snp_etf import load_industry_etf_tickers


@dataclass(frozen=True)
class UniverseSpec:
    key: str
    name: str
    description: str | None
    provider: str
    symbols: tuple[str, ...] = ()


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
    "bluechip_etfs": UniverseSpec(
        key="bluechip_etfs",
        name="Blue-chip ETFs",
        description="Curated large-cap and dividend-quality ETF basket.",
        provider="static",
        symbols=("SPY", "DIA", "QQQ", "SCHD", "VIG"),
    ),
    "industry_etfs": UniverseSpec(
        key="industry_etfs",
        name="Industry ETF",
        description="Sector and industry ETFs used as proxies for S&P 500 stocks.",
        provider="static",
        symbols=load_industry_etf_tickers(),
    ),
}
