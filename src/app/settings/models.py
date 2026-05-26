from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.config.models import AnalyzerConfig, BacktestExecutionConfig, BrokerConfig


SUPPORTED_RESOLUTIONS = ("1m", "5m", "15m", "1h", "1d")
SUPPORTED_FEEDS = ("iex", "sip", "otc")


class AppearanceDefaults(BaseModel):
    theme_mode: Literal["dark", "light", "system"] = "dark"
    density: Literal["comfortable", "compact"] = "comfortable"
    chart_up_color: str = "#26a69a"
    chart_down_color: str = "#ef5350"
    chart_grid_visible: bool = True
    indicator_contrast: Literal["balanced", "high"] = "balanced"
    layout_width: Literal["standard", "wide"] = "standard"
    reduced_motion: bool = False
    time_display_format: Literal["12h", "24h"] = "24h"

    @field_validator("chart_up_color", "chart_down_color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) != 7 or not normalized.startswith("#"):
            raise ValueError("color values must use #RRGGBB format")
        int(normalized[1:], 16)
        return normalized.lower()


class BacktestDefaults(BaseModel):
    symbols_seed_list: list[str] = Field(default_factory=lambda: ["AAPL"], min_length=1)
    date_range_preset: Literal["30D", "90D", "1Y"] = "30D"
    resolution: Literal["1m", "5m", "15m", "1h", "1d"] = "1d"
    feed: Literal["iex", "sip", "otc"] = "iex"
    broker: BrokerConfig = Field(default_factory=BrokerConfig)
    analyzers: AnalyzerConfig = Field(
        default_factory=lambda: AnalyzerConfig(
            include_equity_curve=False,
            include_trade_log=True,
            include_order_log=True,
        )
    )
    execution: BacktestExecutionConfig = Field(default_factory=BacktestExecutionConfig)

    @field_validator("symbols_seed_list")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            symbol = item.strip().upper()
            if not symbol:
                raise ValueError("symbols_seed_list must not contain empty values")
            if symbol not in normalized:
                normalized.append(symbol)
        if not normalized:
            raise ValueError("symbols_seed_list must include at least one symbol")
        return normalized


class PlatformBehaviorSettings(BaseModel):
    timezone: str = "America/New_York"
    auto_refresh_interval_seconds: float = Field(default=1.5, ge=0.5, le=60)
    confirm_before_launch: bool = False
    preferred_landing_page: Literal["backtests", "new_backtest", "chart"] = "backtests"
    backtest_execution_backend: Literal["local", "argo"] = "local"
    argo_split_by: Literal["run", "symbol", "strategy", "symbol_strategy"] = "symbol_strategy"


class PlatformSettings(BaseModel):
    backtest_defaults: BacktestDefaults = Field(default_factory=BacktestDefaults)
    platform_behavior: PlatformBehaviorSettings = Field(default_factory=PlatformBehaviorSettings)


AnalyzerDefaults = AnalyzerConfig
