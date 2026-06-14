from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_SNP_ETF_JSON_PATH = Path(__file__).resolve().parents[3] / "resources" / "snp_etf.json"


@lru_cache(maxsize=1)
def load_industry_etf_tickers() -> tuple[str, ...]:
    payload = json.loads(_SNP_ETF_JSON_PATH.read_text(encoding="utf-8"))
    tickers: set[str] = set()
    for row in payload:
        for field in ("sectorETFs", "industryETFs"):
            for item in row.get(field, []):
                ticker = str(item).strip().upper()
                if ticker:
                    tickers.add(ticker)
    return tuple(sorted(tickers))
