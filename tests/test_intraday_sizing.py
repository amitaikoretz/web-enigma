from __future__ import annotations

import pandas as pd

from app.intraday.models import IntradayCostConfig, IntradaySizingConfig
from app.intraday.pipeline import _size_position


def test_intraday_sizing_threshold_and_monotonicity() -> None:
    row = pd.Series(
        {
            "symbol": "TEST",
            "timestamp": pd.Timestamp("2024-01-01T00:00:00Z"),
            "entry_price": 100.0,
            "volume_1": 50_000.0,
            "dollar_volume_20": 5_000_000.0,
        }
    )
    sizing = IntradaySizingConfig(account_equity=100000.0, max_participation_rate=0.02, max_notional_fraction=0.02)
    costs = IntradayCostConfig(spread_bps=1.0, slippage_bps=1.0, impact_bps=0.5)

    inactive = _size_position(
        row=row,
        expected_edge_bps=1.0,
        forecast_risk_bps=10.0,
        threshold_bps=5.0,
        target_edge_bps=10.0,
        sizing=sizing,
        costs=costs,
        max_risk_fraction=0.001,
        allow_short=True,
    )
    weak = _size_position(
        row=row,
        expected_edge_bps=8.0,
        forecast_risk_bps=10.0,
        threshold_bps=5.0,
        target_edge_bps=10.0,
        sizing=sizing,
        costs=costs,
        max_risk_fraction=0.001,
        allow_short=True,
    )
    strong = _size_position(
        row=row,
        expected_edge_bps=20.0,
        forecast_risk_bps=10.0,
        threshold_bps=5.0,
        target_edge_bps=10.0,
        sizing=sizing,
        costs=costs,
        max_risk_fraction=0.001,
        allow_short=True,
    )

    assert inactive.final_shares == 0.0
    assert 0.0 < weak.final_shares <= strong.final_shares

