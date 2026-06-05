from __future__ import annotations

from datetime import date, datetime
from math import isnan
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.config.models import AnalyzerConfig, BacktestExecutionConfig, BacktestModelPolicyConfig, BrokerConfig
from app.output.models import BacktestReport
from app.output.models import TradeRecord
from app.strategies.exit_rules import ExitRulesSelection
from app.strategies.triggers import TRIGGER_REGISTRY, TriggerSelection, validate_trigger_params


SUPPORTED_RESOLUTIONS = ("1m", "5m", "15m", "1h", "1d")

BacktestJobStatus = Literal["pending", "running", "completed", "failed"]
BacktestExecutionBackend = Literal["local", "argo"]
ArgoSplitBy = Literal["run", "symbol", "trigger", "symbol_trigger"]


def _sanitize_strategy_params(params: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        if isinstance(value, float) and isnan(value):
            continue
        cleaned[key] = value
    return cleaned


class BacktestTriggerSelection(TriggerSelection):
    @model_validator(mode="after")
    def sanitize_params(self) -> "BacktestTriggerSelection":
        if self.name not in TRIGGER_REGISTRY:
            available = ", ".join(sorted(TRIGGER_REGISTRY.keys()))
            raise ValueError(f"Unknown trigger '{self.name}'. Available: {available}")
        self.params = validate_trigger_params(self.name, _sanitize_strategy_params(self.params))
        return self


class BacktestCreateRequest(BaseModel):
    name: str | None = Field(default=None, description="Optional display name for this backtest")
    start_date: date
    end_date: date
    resolution: str = Field(description="Bar resolution such as 1m, 5m, 15m, 1h, or 1d")
    feed: Literal["iex", "sip", "otc"] = "iex"
    symbols: list[str] = Field(min_length=1)
    triggers: list[BacktestTriggerSelection] = Field(min_length=1)
    exit_rules: list[ExitRulesSelection] = Field(min_length=1)
    model_policy: BacktestModelPolicyConfig | None = None
    broker: BrokerConfig | None = None
    analyzers: AnalyzerConfig | None = None
    execution: BacktestExecutionConfig | None = None

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        if value not in SUPPORTED_RESOLUTIONS:
            supported = ", ".join(SUPPORTED_RESOLUTIONS)
            raise ValueError(f"resolution must be one of: {supported}")
        return value

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        for value in values:
            item = value.strip().upper()
            if not item:
                raise ValueError("symbols must not contain empty values")
            if item not in normalized:
                normalized.append(item)
        if not normalized:
            raise ValueError("At least one symbol is required")
        return normalized

    @model_validator(mode="after")
    def validate_dates(self) -> "BacktestCreateRequest":
        if self.start_date > self.end_date:
            raise ValueError("start_date must be <= end_date")
        return self

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("name must be a string")
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > 256:
            raise ValueError("name must be at most 256 characters")
        return trimmed


class BacktestSelectionSummary(BaseModel):
    start_date: date
    end_date: date
    resolution: str
    feed: Literal["iex", "sip", "otc"]
    symbols: list[str]
    triggers: list[str]
    exit_rules: list[str]

    @model_validator(mode="before")
    @classmethod
    def _coerce_legacy_fields(cls, data: Any) -> Any:
        """
        Backward-compat for persisted DB rows created before the trigger/exit_rules split.

        Note: user-facing backtest config does not support legacy strategy fields; this
        is only for reading old selection summaries already stored in the database.
        """
        if not isinstance(data, dict):
            return data

        # Legacy: "strategies": ["sma_cross", ...] -> "triggers": [...]
        if "triggers" not in data:
            legacy_strategies = data.get("strategies")
            if isinstance(legacy_strategies, list) and all(isinstance(x, str) for x in legacy_strategies):
                data = {**data, "triggers": legacy_strategies}
            else:
                legacy_strategy = data.get("strategy")
                if isinstance(legacy_strategy, str) and legacy_strategy.strip():
                    data = {**data, "triggers": [legacy_strategy.strip()]}

        # Exit rules didn't exist previously; keep validation happy with a sentinel.
        if "exit_rules" not in data:
            data = {**data, "exit_rules": ["unknown"]}

        return data


class BacktestArtifactSummaryItem(BaseModel):
    kind: str
    label: str
    description: str = ""
    format: BacktestArtifactFormat
    role: BacktestArtifactRole


class BacktestListItem(BaseModel):
    id: str
    name: str | None = None
    created_at: datetime
    updated_at: datetime
    status: BacktestJobStatus
    report_status: Literal["success", "partial_failure", "failure"] | None = None
    total_runs: int
    completed_runs: int = 0
    successful_runs: int = 0
    failed_runs: int = 0
    selection: BacktestSelectionSummary | None = None
    error_message: str | None = None
    execution_backend: BacktestExecutionBackend = "local"
    workflow_name: str | None = None
    workflow_namespace: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    stored_artifacts: list[BacktestArtifactSummaryItem] = Field(default_factory=list)


class BacktestListItemWithProgress(BacktestListItem):
    progress_pct: float = Field(ge=0, le=100)
    progress_source: Literal["runs", "argo"] = "runs"


class BacktestListPageResponse(BaseModel):
    items: list[BacktestListItemWithProgress]
    total: int
    page: int
    page_size: int


class BacktestCreateResponse(BaseModel):
    backtest_id: str
    status: BacktestJobStatus
    status_url: str
    detail_url: str
    source_backtest_id: str | None = None


class BacktestArgoLaunchRequest(BaseModel):
    config_path: str | None = None
    config_text: str | None = None
    format: Literal["json", "yaml"] = "yaml"
    split_by: ArgoSplitBy | None = None
    backtest_id: str | None = None
    name: str | None = None

    @model_validator(mode="after")
    def validate_input_mode(self) -> "BacktestArgoLaunchRequest":
        has_path = bool(self.config_path and self.config_path.strip())
        has_text = bool(self.config_text and self.config_text.strip())
        if has_path == has_text:
            raise ValueError("Provide exactly one of config_path or config_text")
        return self


class BacktestArgoLaunchResponse(BaseModel):
    backtest_id: str
    workflow_name: str
    status: BacktestJobStatus
    status_url: str
    detail_url: str
    workflow_namespace: str
    config_path: str
    output_path: str


class BacktestStatusResponse(BacktestListItem):
    progress_pct: float = Field(ge=0, le=100)
    is_terminal: bool


class BacktestRetryRequest(BaseModel):
    force: bool = Field(
        default=False,
        description="Allow retry even when the source backtest is still active (creates a new backtest id).",
    )
    config_text: str | None = Field(
        default=None,
        description="Optional inline config override (YAML or JSON). When provided, the new backtest is launched from this config instead of the stored source config.",
    )
    format: Literal["json", "yaml"] = Field(default="yaml", description="Format of config_text when provided.")


class BacktestConfigUpdateRequest(BaseModel):
    config_text: str = Field(description="New backtest config content (YAML or JSON).")
    format: Literal["json", "yaml"] = "yaml"


class BacktestUpdateRequest(BaseModel):
    name: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise TypeError("name must be a string")
        trimmed = value.strip()
        if not trimmed:
            return None
        if len(trimmed) > 256:
            raise ValueError("name must be at most 256 characters")
        return trimmed


BacktestArtifactFormat = Literal["json", "yaml", "parquet", "other"]
BacktestArtifactRole = Literal["primary", "sidecar", "manifest", "shard"]


class BacktestArtifactEntry(BaseModel):
    kind: str
    label: str
    description: str = ""
    format: BacktestArtifactFormat
    role: BacktestArtifactRole
    path: str
    size_bytes: int | None = None


class BacktestDetailResponse(BaseModel):
    metadata: BacktestListItem
    output_path: str | None = None
    report: BacktestReport | None = None
    artifacts: list[BacktestArtifactEntry] = Field(default_factory=list)


class BacktestTradeReplayCapsule(BaseModel):
    capsule_version: int = 1
    backtest_id: str
    run_id: str
    run_name: str | None = None
    run_symbol: str | None = None
    run_strategy: str
    trade_index: int = Field(ge=0)
    target_methods: list[str] = Field(default_factory=list)
    break_at: Literal["entry", "exit"] = "entry"
    trade: TradeRecord
    trade_entry_time: str | None = None
    trade_exit_time: str | None = None
    focus_window_start: str | None = None
    focus_window_end: str | None = None
    config_format: Literal["yaml"] = "yaml"
    config_text: str = Field(min_length=1)
    config_sha256: str | None = None


class BacktestTradeReplayResponse(BaseModel):
    capsule: BacktestTradeReplayCapsule
    launch_config: dict[str, object]
