from __future__ import annotations

import pandas as pd

from app.api.schemas.market_data import MarketDataRow


def frame_to_rows(frame: pd.DataFrame) -> list[MarketDataRow]:
    rows: list[MarketDataRow] = []
    for timestamp, record in frame.iterrows():
        rows.append(
            MarketDataRow(
                timestamp=pd.Timestamp(timestamp).isoformat(),
                open=float(record["Open"]),
                high=float(record["High"]),
                low=float(record["Low"]),
                close=float(record["Close"]),
                volume=float(record["Volume"]),
            )
        )
    return rows
