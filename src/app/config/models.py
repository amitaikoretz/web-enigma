from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.strategies.registry import STRATEGY_REGISTRY, validate_strategy_params


class BrokerConfig(BaseModel):
    cash: float = Field(default=10000.0, gt=0)
    commission: float = Field(default=0.0, ge=0)
    slippage_perc: float = Field(default=0.0005, ge=0)
    sizer: Literal["fixed"] = "fixed"


class AnalyzerConfig(BaseModel):
    include_equity_curve: bool = True
    include_trade_log: bool = True
    include_order_log: bool = True
    include_candidate_log: bool = False


class BacktestExecutionConfig(BaseModel):
    fill_model: Literal["close", "next_bar"] = "close"


class DataCacheConfig(BaseModel):
    enabled: bool = True
    directory: str = ".cache/backtest-data"
    refresh_policy: Literal["ttl"] = "ttl"
    ttl_by_interval: dict[str, int] = Field(
        default_factory=lambda: {
            "1m": 10 * 60,
            "5m": 30 * 60,
            "15m": 60 * 60,
            "1h": 6 * 60 * 60,
            "1d": 24 * 60 * 60,
        }
    )


class CsvDataSource(BaseModel):
    type: Literal["csv"]
    path: str
    datetime_column: str = "datetime"
    open_column: str = "open"
    high_column: str = "high"
    low_column: str = "low"
    close_column: str = "close"
    volume_column: str = "volume"
    openinterest_column: str = "openinterest"
    date_format: str = "%Y-%m-%d"


class YahooDataSource(BaseModel):
    type: Literal["yahoo"]
    symbol: str
    interval: str = "1d"


class AlpacaDataSource(BaseModel):
    type: Literal["alpaca"]
    symbol: str
    interval: str = "1d"
    feed: Literal["iex", "sip", "otc"] = "iex"


DataSource = CsvDataSource | YahooDataSource | AlpacaDataSource


class StrategyConfig(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_strategy(self) -> "StrategyConfig":
        if self.name not in STRATEGY_REGISTRY:
            available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
            raise ValueError(f"Unknown strategy '{self.name}'. Available: {available}")
        self.params = validate_strategy_params(self.name, self.params)
        return self


class BacktestRunConfig(BaseModel):
    run_id: str
    name: str | None = None
    start_date: date
    end_date: date
    data: DataSource
    strategy: str | None = None
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    strategies: list[StrategyConfig] | None = None
    broker: BrokerConfig | None = None
    analyzers: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    execution: BacktestExecutionConfig = Field(default_factory=BacktestExecutionConfig)

    @model_validator(mode="after")
    def validate_dates(self) -> "BacktestRunConfig":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self

    @model_validator(mode="after")
    def validate_strategy(self) -> "BacktestRunConfig":
        has_single = self.strategy is not None
        has_multi = bool(self.strategies)
        if not has_single and not has_multi:
            raise ValueError("Run must define either 'strategy' or a non-empty 'strategies' list")

        if has_single:
            assert self.strategy is not None
            if self.strategy not in STRATEGY_REGISTRY:
                available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
                raise ValueError(f"Unknown strategy '{self.strategy}'. Available: {available}")
            self.strategy_params = validate_strategy_params(self.strategy, self.strategy_params)

        if has_multi and self.strategies is not None:
            names = [s.name for s in self.strategies]
            if len(names) != len(set(names)):
                raise ValueError("strategy names in 'strategies' must be unique within a run")
        return self


class GlobalConfig(BaseModel):
    timezone: str = "UTC"
    default_broker: BrokerConfig = Field(default_factory=BrokerConfig)
    data_cache: DataCacheConfig = Field(default_factory=DataCacheConfig)


class WorkflowConfig(BaseModel):
    split_by: Literal["run", "symbol", "strategy", "symbol_strategy"] | None = None


class BacktestConfig(BaseModel):
    global_config: GlobalConfig = Field(default_factory=GlobalConfig)
    workflow: WorkflowConfig | None = None
    runs: list[BacktestRunConfig]

    @model_validator(mode="after")
    def ensure_runs(self) -> "BacktestConfig":
        if not self.runs:
            raise ValueError("At least one run is required")
        ids = [r.run_id for r in self.runs]
        if len(ids) != len(set(ids)):
            raise ValueError("run_id values must be unique")
        return self


class AlpacaExecutionConfig(BaseModel):
    mode: Literal["paper", "live"] = "paper"
    poll_interval_seconds: int = Field(default=60, ge=1)
    state_directory: str = ".cache/alpaca-runtime"
    include_candidate_log: bool = False


class AlpacaTradingRunConfig(BaseModel):
    run_id: str
    name: str | None = None
    symbol: str
    interval: str = "1m"
    feed: Literal["iex", "sip", "otc"] = "iex"
    strategy: str
    strategy_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_strategy(self) -> "AlpacaTradingRunConfig":
        if self.strategy not in STRATEGY_REGISTRY:
            available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
            raise ValueError(f"Unknown strategy '{self.strategy}'. Available: {available}")
        self.strategy_params = validate_strategy_params(self.strategy, self.strategy_params)
        return self


class AlpacaTradingGlobalConfig(BaseModel):
    timezone: str = "UTC"
    execution: AlpacaExecutionConfig = Field(default_factory=AlpacaExecutionConfig)


class AlpacaTradingConfig(BaseModel):
    global_config: AlpacaTradingGlobalConfig = Field(default_factory=AlpacaTradingGlobalConfig)
    runs: list[AlpacaTradingRunConfig]

    @model_validator(mode="after")
    def ensure_runs(self) -> "AlpacaTradingConfig":
        if not self.runs:
            raise ValueError("At least one run is required")
        ids = [r.run_id for r in self.runs]
        if len(ids) != len(set(ids)):
            raise ValueError("run_id values must be unique")
        return self


class RedisConfig(BaseModel):
    url: str = "redis://localhost:6379/0"
    key_prefix: str = "ta"
    assignment_poll_interval_seconds: float = Field(default=2.0, gt=0)
    lease_ttl_seconds: int = Field(default=20, ge=5)
    heartbeat_interval_seconds: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def validate_lease_timing(self) -> "RedisConfig":
        if self.heartbeat_interval_seconds >= self.lease_ttl_seconds:
            raise ValueError("heartbeat_interval_seconds must be less than lease_ttl_seconds")
        return self


class PostgresRuntimeConfig(BaseModel):
    database_url_env: str = "DATABASE_URL"
    broker_name: str = "alpaca"
    run_mode: Literal["paper_live", "paper_replay", "simulated"] = "paper_live"


class SessionConfig(BaseModel):
    timezone: str = "America/New_York"
    pre_open_warmup_minutes: int = Field(default=15, ge=0)
    drain_timeout_minutes: int = Field(default=15, ge=1)
    flatten_positions_by_close: bool = True
    allow_exit_orders_during_drain: bool = True


class ReplayConfig(BaseModel):
    enabled: bool = False
    speed_multiplier: float = Field(default=1.0, gt=0)
    historical_source: Literal["alpaca", "csv"] = "alpaca"
    broker_mode: Literal["simulated", "paper"] = "simulated"


class ControllerConfig(BaseModel):
    contracts_api_base_url: str = "http://localhost:8000"
    poll_interval_seconds: int = Field(default=5, ge=1)
    shard_count: int = Field(default=2, ge=1)
    scale_up_replicas: int | None = Field(default=None, ge=1)
    enable_kubernetes_scaling: bool = False

    @model_validator(mode="after")
    def default_scale_up_replicas(self) -> "ControllerConfig":
        if self.scale_up_replicas is None:
            self.scale_up_replicas = self.shard_count
        return self


class WorkerConfig(BaseModel):
    shard_id: int = Field(default=0, ge=0)
    feed_poll_interval_seconds: float = Field(default=1.0, gt=0)
    warmup_bars: int = Field(default=100, ge=1)
    drain_timeout_seconds: int = Field(default=300, ge=1)
    worker_id: str | None = None


class LiveTradingGlobalConfig(BaseModel):
    redis: RedisConfig = Field(default_factory=RedisConfig)
    runtime: PostgresRuntimeConfig = Field(default_factory=PostgresRuntimeConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    replay: ReplayConfig = Field(default_factory=ReplayConfig)
    controller: ControllerConfig = Field(default_factory=ControllerConfig)
    worker: WorkerConfig = Field(default_factory=WorkerConfig)
    execution: AlpacaExecutionConfig = Field(default_factory=AlpacaExecutionConfig)


class LiveTradingContractConfig(BaseModel):
    contract_id: str | None = None
    symbol: str
    interval: str = "1m"
    feed: Literal["iex", "sip", "otc"] = "iex"
    strategy: str
    strategy_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_strategy(self) -> "LiveTradingContractConfig":
        if self.strategy not in STRATEGY_REGISTRY:
            available = ", ".join(sorted(STRATEGY_REGISTRY.keys()))
            raise ValueError(f"Unknown strategy '{self.strategy}'. Available: {available}")
        self.strategy_params = validate_strategy_params(self.strategy, self.strategy_params)
        return self


class LiveTradingConfig(BaseModel):
    global_config: LiveTradingGlobalConfig = Field(default_factory=LiveTradingGlobalConfig)
    contracts: list[LiveTradingContractConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_contracts(self) -> "LiveTradingConfig":
        seen_ids = [contract.contract_id for contract in self.contracts if contract.contract_id is not None]
        if len(seen_ids) != len(set(seen_ids)):
            raise ValueError("contract_id values must be unique when provided")
        return self
