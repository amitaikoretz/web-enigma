from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationInfo, model_validator

from app.strategies.exit_rules import ExitRulesSelection
from app.strategies.exit_rules import get_exit_rule_spec
from app.strategies.triggers import TriggerSelection
from app.strategies.yaml_io import load_exit_rules_selection, load_trigger_selection


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
    include_risk_auxiliary: bool = False

    @model_validator(mode="after")
    def ensure_risk_auxiliary_requires_candidates(self) -> "AnalyzerConfig":
        if self.include_risk_auxiliary:
            object.__setattr__(self, "include_candidate_log", True)
        return self


class BacktestExecutionConfig(BaseModel):
    fill_model: Literal["close", "next_bar"] = "close"


class ModelArtifactRef(BaseModel):
    group_id: str | None = None
    model_artifact_path: str | None = None
    target_key: str | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> "ModelArtifactRef":
        has_group_id = bool(self.group_id and self.group_id.strip())
        has_artifact_path = bool(self.model_artifact_path and self.model_artifact_path.strip())
        if has_group_id == has_artifact_path:
            raise ValueError("Provide exactly one of 'group_id' or 'model_artifact_path'")
        if self.group_id is not None:
            object.__setattr__(self, "group_id", self.group_id.strip())
        if self.model_artifact_path is not None:
            object.__setattr__(self, "model_artifact_path", self.model_artifact_path.strip())
        if self.target_key is not None:
            target_key = self.target_key.strip()
            object.__setattr__(self, "target_key", target_key or None)
        return self

    def resolve_paths(self, *, base_dir: Path) -> "ModelArtifactRef":
        if self.model_artifact_path is None:
            return self
        path = Path(self.model_artifact_path)
        if not path.is_absolute():
            path = (base_dir / path).resolve()
        return self.model_copy(update={"model_artifact_path": str(path)})

    def stable_payload(self) -> dict[str, str | None]:
        return self.model_dump(mode="json")


class BacktestModelPolicyConfig(BaseModel):
    forecast_model: ModelArtifactRef | None = None
    risk_model: ModelArtifactRef | None = None
    threshold_bps: float = Field(default=1.0, ge=0.0)
    target_edge_bps: float = Field(default=5.0, gt=0.0)
    max_risk_fraction: float = Field(default=0.001, gt=0.0, le=1.0)
    allow_short: bool = False
    min_signal_score: float = Field(default=0.0)

    def stable_id(self) -> str:
        payload = self.model_dump(mode="json")
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha1(encoded).hexdigest()[:10]  # noqa: S324


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


class ParquetDataSource(BaseModel):
    type: Literal["parquet"]
    path: str


class YahooDataSource(BaseModel):
    type: Literal["yahoo"]
    symbol: str
    interval: str = "1d"


class AlpacaDataSource(BaseModel):
    type: Literal["alpaca"]
    symbol: str
    interval: str = "1d"
    feed: Literal["iex", "sip", "otc"] = "iex"


class AlpacaOptionsDataSource(BaseModel):
    type: Literal["alpaca-options"]
    symbol: str
    interval: str = "1d"
    feed: Literal["indicative", "opra"] = "indicative"


DataSource = CsvDataSource | ParquetDataSource | YahooDataSource | AlpacaDataSource | AlpacaOptionsDataSource


class BacktestRunConfig(BaseModel):
    run_id: str
    name: str | None = None
    start_date: date
    end_date: date
    data: DataSource
    trigger_path: str | None = None
    exit_rules_path: str | None = None
    trigger: TriggerSelection | None = None
    exit_rules: ExitRulesSelection | None = None
    model_policy: BacktestModelPolicyConfig | None = None
    broker: BrokerConfig | None = None
    analyzers: AnalyzerConfig = Field(default_factory=AnalyzerConfig)
    execution: BacktestExecutionConfig = Field(default_factory=BacktestExecutionConfig)

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_strategy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        raw = dict(data)

        # Legacy single-strategy shape: `strategy` + `strategy_params`.
        strategy = raw.get("strategy")
        if raw.get("trigger") is None and isinstance(strategy, str) and strategy.strip():
            legacy_params = raw.get("strategy_params")
            if not isinstance(legacy_params, dict):
                legacy_params = {}
            trigger_name = _legacy_trigger_name_for_strategy(strategy.strip())
            if trigger_name is None:
                trigger_name = strategy.strip()
            raw["trigger"] = {"name": trigger_name, "params": legacy_params}
            if raw.get("exit_rules") is None:
                exit_rules = _legacy_exit_rules_for_strategy(strategy.strip(), legacy_params)
                if exit_rules is not None:
                    raw["exit_rules"] = exit_rules.model_dump(mode="json")
            raw.pop("strategy", None)
            raw.pop("strategy_params", None)

        # Legacy multi-strategy shape: `strategies` is a list of strategy selections.
        strategies = raw.get("strategies")
        if raw.get("trigger") is None and isinstance(strategies, list):
            entries = [entry for entry in strategies if isinstance(entry, dict)]
            if len(entries) == 1:
                entry = entries[0]
                strategy_name = entry.get("name")
                legacy_params = entry.get("params")
                if isinstance(strategy_name, str) and strategy_name.strip():
                    if not isinstance(legacy_params, dict):
                        legacy_params = {}
                    raw["trigger"] = {"name": strategy_name.strip(), "params": legacy_params}
                    if raw.get("exit_rules") is None:
                        exit_rules = _legacy_exit_rules_for_strategy(strategy_name.strip(), legacy_params)
                        if exit_rules is not None:
                            raw["exit_rules"] = exit_rules.model_dump(mode="json")
                    raw.pop("strategies", None)
            elif len(entries) > 1:
                raise ValueError(
                    "Legacy multi-strategy runs are no longer supported; split each strategy into its own "
                    "run with trigger/exit_rules."
                )

        return raw

    @model_validator(mode="after")
    def validate_dates(self) -> "BacktestRunConfig":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self

    @model_validator(mode="after")
    def resolve_components(self, info: ValidationInfo) -> "BacktestRunConfig":
        base_dir = info.context.get("config_base_dir") if info.context else None
        if base_dir is None:
            base_dir = Path(".").resolve()
        elif not isinstance(base_dir, Path):
            base_dir = Path(str(base_dir)).resolve()

        if self.trigger is None:
            if not self.trigger_path:
                raise ValueError("Run must define either 'trigger' or 'trigger_path'")
            self.trigger = load_trigger_selection(self.trigger_path, base_dir=base_dir)

        if self.exit_rules is None:
            if not self.exit_rules_path:
                raise ValueError("Run must define either 'exit_rules' or 'exit_rules_path'")
            self.exit_rules = load_exit_rules_selection(self.exit_rules_path, base_dir=base_dir)

        if self.model_policy is not None:
            if self.model_policy.forecast_model is not None:
                self.model_policy.forecast_model = self.model_policy.forecast_model.resolve_paths(base_dir=base_dir)
            if self.model_policy.risk_model is not None:
                self.model_policy.risk_model = self.model_policy.risk_model.resolve_paths(base_dir=base_dir)
        return self


class GlobalConfig(BaseModel):
    timezone: str = "UTC"
    default_broker: BrokerConfig = Field(default_factory=BrokerConfig)
    data_cache: DataCacheConfig = Field(default_factory=DataCacheConfig)


class WorkflowConfig(BaseModel):
    split_by: Literal["run", "symbol", "trigger", "symbol_trigger"] | None = None


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
    trigger_path: str | None = None
    exit_rules_path: str | None = None
    trigger: TriggerSelection | None = None
    exit_rules: ExitRulesSelection | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_legacy_strategy_fields(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        raw = dict(data)
        strategy = raw.get("strategy")
        if raw.get("trigger") is None and isinstance(strategy, str) and strategy.strip():
            legacy_params = raw.get("strategy_params")
            if not isinstance(legacy_params, dict):
                legacy_params = {}
            trigger_name = _legacy_trigger_name_for_strategy(strategy.strip())
            if trigger_name is None:
                trigger_name = strategy.strip()
            raw["trigger"] = {"name": trigger_name, "params": legacy_params}
            if raw.get("exit_rules") is None:
                exit_rules = _legacy_exit_rules_for_strategy(strategy.strip(), legacy_params)
                if exit_rules is not None:
                    raw["exit_rules"] = exit_rules.model_dump(mode="json")
            raw.pop("strategy", None)
            raw.pop("strategy_params", None)
        return raw

    @model_validator(mode="after")
    def resolve_components(self, info: ValidationInfo) -> "AlpacaTradingRunConfig":
        base_dir = info.context.get("config_base_dir") if info.context else None
        if base_dir is None:
            base_dir = Path(".").resolve()
        elif not isinstance(base_dir, Path):
            base_dir = Path(str(base_dir)).resolve()

        if self.trigger is None:
            if not self.trigger_path:
                raise ValueError("Run must define either 'trigger' or 'trigger_path'")
            self.trigger = load_trigger_selection(self.trigger_path, base_dir=base_dir)

        if self.exit_rules is None:
            if not self.exit_rules_path:
                raise ValueError("Run must define either 'exit_rules' or 'exit_rules_path'")
            self.exit_rules = load_exit_rules_selection(self.exit_rules_path, base_dir=base_dir)
        return self


_LEGACY_STRATEGY_EXIT_RULES: dict[str, list[str]] = {
    "sma_cross": ["sma_cross_down", "fixed_pct_oco", "max_hold_bars"],
    "rsi_reversion": ["rsi_overbought", "fixed_pct_oco", "max_hold_bars"],
    "buy_and_hold": ["fixed_pct_oco", "max_hold_bars"],
    "breakout_channel": ["channel_break", "fixed_pct_oco", "max_hold_bars"],
    "buy_oco_atr_tp_sl": ["atr_oco", "max_hold_bars"],
    "buy_oco_atr_tp_trailing": ["atr_trailing", "max_hold_bars"],
    "fast_upswing": ["volume_rally_atr"],
    "volume_rally": ["volume_rally_atr"],
}

_LEGACY_STRATEGY_TRIGGER_NAMES: dict[str, str] = {
    "buy_oco_atr_tp_sl": "buy_oco_atr",
    "buy_oco_atr_tp_trailing": "buy_oco_atr",
}


def _legacy_trigger_name_for_strategy(strategy_name: str) -> str | None:
    return _LEGACY_STRATEGY_TRIGGER_NAMES.get(strategy_name)


def _legacy_exit_rules_for_strategy(strategy_name: str, params: dict[str, Any]) -> ExitRulesSelection | None:
    rule_names = _LEGACY_STRATEGY_EXIT_RULES.get(strategy_name)
    if not rule_names:
        return None

    rules: list[dict[str, Any]] = []
    for rule_name in rule_names:
        spec = get_exit_rule_spec(rule_name)
        rule_params = {key: value for key, value in params.items() if key in spec.params_model.model_fields}
        rules.append({"name": rule_name, "params": rule_params})

    return ExitRulesSelection.model_validate({"rules": rules})


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
    trigger: TriggerSelection
    exit_rules: ExitRulesSelection

    @model_validator(mode="after")
    def normalize_symbol(self) -> "LiveTradingContractConfig":
        self.symbol = self.symbol.strip().upper()
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
