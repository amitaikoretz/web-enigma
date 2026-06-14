from __future__ import annotations

from app.universes.snp_etf import load_industry_etf_tickers

EXPECTED_INDUSTRY_ETFS = (
    "FCOM",
    "FDIS",
    "FTEC",
    "IDU",
    "IXC",
    "IXJ",
    "IYF",
    "IYJ",
    "IYK",
    "IYM",
    "IYR",
    "SCHH",
    "VAW",
    "VCR",
    "VDC",
    "VDE",
    "VFH",
    "VGT",
    "VHT",
    "VIS",
    "VNQ",
    "VOX",
    "VPU",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLU",
    "XLV",
    "XLY",
)


def test_load_industry_etf_tickers_returns_sector_and_industry_etfs() -> None:
    tickers = load_industry_etf_tickers()
    assert tickers == EXPECTED_INDUSTRY_ETFS
    assert len(tickers) == 33
