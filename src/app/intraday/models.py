from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.config.models import AlpacaDataSource, CsvDataSource, DataCacheConfig, YahooDataSource

DataSource = CsvDataSource | YahooDataSource | AlpacaDataSource
ForecastDirection = Literal["LONG", "SHORT", "FLAT"]


class IntradaySeriesSpec(BaseModel):
    symbol: str | None = None
    data: DataSource

    @model_validator(mode="after")
    def ensure_symbol(self) -> "IntradaySeriesSpec":
        if self.symbol is None:
            if isinstance(self.data, (YahooDataSource, AlpacaDataSource)):
                object.__setattr__(self, "symbol", self.data.symbol)
        return self


class IntradayUniverseConfig(BaseModel):
    start_date: date
    end_date: date
    interval: str = "5m"
    symbols: list[IntradaySeriesSpec]
    benchmark: IntradaySeriesSpec | None = None

    @model_validator(mode="after")
    def validate_universe(self) -> "IntradayUniverseConfig":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        if not self.symbols:
            raise ValueError("At least one symbol is required")

        intervals = {spec.data.interval for spec in self.symbols if hasattr(spec.data, "interval")}
        if len(intervals) > 1:
            raise ValueError("All symbol data sources must use the same interval in v1")
        if intervals and self.interval not in intervals:
            raise ValueError("Universe interval must match symbol data source interval")

        if self.benchmark is not None:
            benchmark_intervals = {self.benchmark.data.interval} if hasattr(self.benchmark.data, "interval") else set()
            if benchmark_intervals and self.interval not in benchmark_intervals:
                raise ValueError("Benchmark data source must use the same interval as the universe")
        return self


class IntradayWalkForwardConfig(BaseModel):
    train_days: int = Field(default=60, gt=0)
    validation_days: int = Field(default=5, gt=0)
    test_days: int = Field(default=5, gt=0)
    step_days: int = Field(default=5, gt=0)
    embargo_bars: int = Field(default=1, ge=0)
    min_train_rows: int = Field(default=200, gt=0)
    min_validation_rows: int = Field(default=50, gt=0)
    min_test_rows: int = Field(default=50, gt=0)


class IntradayModelSearchConfig(BaseModel):
    alpha_grid: list[float] = Field(default_factory=lambda: [0.1, 1.0, 10.0])
    threshold_bps_grid: list[float] = Field(default_factory=lambda: [1.0, 2.5, 5.0, 10.0])
    max_risk_fraction_grid: list[float] = Field(default_factory=lambda: [0.0005, 0.001, 0.0025])
    target_edge_bps_grid: list[float] = Field(default_factory=lambda: [5.0, 10.0, 20.0])
    n_quantile_bins: int = Field(default=10, ge=2)


class IntradayCostConfig(BaseModel):
    spread_bps: float = Field(default=1.5, ge=0)
    slippage_bps: float = Field(default=1.0, ge=0)
    impact_bps: float = Field(default=0.5, ge=0)

    @property
    def roundtrip_bps(self) -> float:
        return 2.0 * self.spread_bps + 2.0 * self.slippage_bps + self.impact_bps


class IntradaySizingConfig(BaseModel):
    account_equity: float = Field(default=100000.0, gt=0)
    max_participation_rate: float = Field(default=0.02, gt=0, le=1)
    max_notional_fraction: float = Field(default=0.02, gt=0, le=1)
    target_vol_bps: float = Field(default=20.0, gt=0)
    floor_vol_bps: float = Field(default=5.0, gt=0)
    stop_vol_multiplier: float = Field(default=1.5, gt=0)
    min_stop_bps: float = Field(default=5.0, gt=0)


class IntradayRunConfig(BaseModel):
    model_version: str = "intraday_model_v1"
    feature_version: str = "intraday_features_v1"
    label_version: str = "intraday_labels_v1"
    dataset_version: str = "intraday_dataset_v1"
    data_cache: DataCacheConfig = Field(default_factory=DataCacheConfig)
    universe: IntradayUniverseConfig
    walk_forward: IntradayWalkForwardConfig = Field(default_factory=IntradayWalkForwardConfig)
    model_search: IntradayModelSearchConfig = Field(default_factory=IntradayModelSearchConfig)
    costs: IntradayCostConfig = Field(default_factory=IntradayCostConfig)
    sizing: IntradaySizingConfig = Field(default_factory=IntradaySizingConfig)
    output_dir: str = "artifacts/intraday"
    allow_short: bool = True
    lookback_bars: int = Field(default=60, gt=0)
    horizon_bars: int = Field(default=5, gt=0)


class IntradayDatasetManifest(BaseModel):
    generated_at: datetime
    dataset_version: str
    feature_version: str
    label_version: str
    model_version: str
    config_hash: str
    symbol_count: int
    benchmark_symbol: str | None = None
    start_date: date
    end_date: date
    total_rows: int
    kept_rows: int
    dropped_history_rows: int
    dropped_forward_rows: int
    feature_columns: list[str] = Field(default_factory=list)
    dataset_path: str
    predictions_path: str
    positions_path: str
    model_path: str
    metrics_path: str


class PositionSizingDecision(BaseModel):
    symbol: str
    timestamp: str
    direction: ForecastDirection
    expected_edge_bps: float
    forecast_risk_bps: float
    threshold_bps: float
    quality_scale: float
    vol_scale: float
    risk_based_shares: float
    liquidity_cap_shares: float
    final_shares: float
    final_notional: float
    entry_price: float
    stop_distance_bps: float
    roundtrip_cost_bps: float
    fold_id: int | None = None
    reason: str | None = None


class IntradayModelArtifact(BaseModel):
    model_version: str
    feature_version: str
    label_version: str
    dataset_version: str
    fold_id: int
    selected_features: list[str] = Field(default_factory=list)
    scaler_mean: list[float] = Field(default_factory=list)
    scaler_scale: list[float] = Field(default_factory=list)
    coefficients: list[float] = Field(default_factory=list)
    intercept: float
    residual_std: float
    walk_forward: dict[str, Any] = Field(default_factory=dict)
    costs: dict[str, float] = Field(default_factory=dict)
    sizing: dict[str, float] = Field(default_factory=dict)
    selected_hyperparameters: dict[str, float] = Field(default_factory=dict)
    validation_metrics: dict[str, float | None] = Field(default_factory=dict)
    test_metrics: dict[str, float | None] = Field(default_factory=dict)


class IntradayRunMetrics(BaseModel):
    generated_at: datetime
    dataset_version: str
    feature_version: str
    label_version: str
    model_version: str
    config_hash: str
    selected_hyperparameters: dict[str, float]
    fold_metrics: list[dict[str, Any]] = Field(default_factory=list)
    aggregate: dict[str, Any] = Field(default_factory=dict)
