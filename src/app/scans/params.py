from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.scans.models import ScanType


class BaseScanParams(BaseModel):
    """
    Typed scan parameters used by the API and the Argo scan runners.

    Notes:
    - These are intentionally "simple JSON" so they round-trip cleanly through
      Argo workflow parameters.
    """


class MomentumScanParams(BaseScanParams):
    # Universe selection
    symbols: list[str] = Field(default_factory=list, description="Explicit symbols to scan (empty = default universe)")
    max_symbols: int = Field(300, ge=1, le=5000)

    # Time horizon / signals
    lookback_days: int = Field(90, ge=20, le=3650)
    min_avg_dollar_volume: float = Field(5_000_000, ge=0)
    min_price: float = Field(5.0, ge=0, description="Reject symbols with last close below this threshold")


class TrendScanParams(BaseScanParams):
    symbols: list[str] = Field(default_factory=list, description="Explicit symbols to scan (empty = default universe)")
    max_symbols: int = Field(300, ge=1, le=5000)
    lookback_days: int = Field(180, ge=20, le=3650)
    min_avg_dollar_volume: float = Field(5_000_000, ge=0)


class OptionsScanParams(BaseScanParams):
    # Universe
    symbols: list[str] = Field(default_factory=list, description="Explicit underlyings (empty = default universe)")
    max_symbols: int = Field(200, ge=1, le=5000)
    min_underlying_price: float = Field(10.0, ge=0)
    min_avg_dollar_volume: float = Field(10_000_000, ge=0)

    # Contract filters
    dte_min: int = Field(14, ge=0, le=3650)
    dte_max: int = Field(45, ge=0, le=3650)
    min_open_interest: int = Field(200, ge=0)
    max_spread_pct: float = Field(0.05, ge=0, le=1.0, description="Max bid/ask spread as fraction of mid")

    # What to scan for (kept minimal for now; scanner implementation is still pending)
    direction: Literal["calls", "puts", "both"] = "calls"


def params_model_for_scan_type(scan_type: ScanType) -> type[BaseScanParams]:
    if scan_type == "momentum":
        return MomentumScanParams
    if scan_type == "options":
        return OptionsScanParams
    if scan_type == "trend":
        return TrendScanParams
    raise ValueError(f"Unsupported scan type: {scan_type}")


def parse_scan_params(scan_type: ScanType, raw: dict[str, Any]) -> BaseScanParams:
    model = params_model_for_scan_type(scan_type)
    return model.model_validate(raw or {})
