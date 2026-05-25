from __future__ import annotations

import json
import tempfile
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from starlette.requests import Request
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
import yaml

from app.config.models import (
    AlpacaDataSource,
    AnalyzerConfig,
    BacktestConfig,
    BrokerConfig,
    DataCacheConfig,
)
from app.api_logging import configure_api_logging
from app.backtests import (
    BacktestCreateRequest,
    BacktestCreateResponse,
    BacktestDetailResponse,
    BacktestJobService,
    BacktestListItem,
    BacktestResultRepository,
    BacktestStatusResponse,
)
from app.contracts import TradingContractActiveQuery, TradingContractCreate, TradingContractResponse, to_contract_record
from app.data.loaders import build_alpaca_data_feed_with_cache
from app.db.models import TradingContract
from app.db.session import get_db_session
from app.engine.runner import run_backtests
from app.output import write_backtest_report_json
from app.output.models import OrderRecord, RunError, RunSummary, TradeRecord
from app.settings import PlatformSettings, PlatformSettingsService
from app.strategies.registry import list_strategies


SUPPORTED_RESOLUTIONS = ("1m", "5m", "15m", "1h", "1d")


class MarketDataRow(BaseModel):
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class MarketDataResponse(BaseModel):
    symbol: str
    provider: Literal["alpaca"]
    resolution: str
    start_date: date
    stop_date: date
    cache_status: str
    rows: list[MarketDataRow]


class StrategyParameterMetadata(BaseModel):
    type: str
    default: Any | None = None
    required: bool
    minimum: float | int | None = None
    maximum: float | int | None = None
    exclusiveMinimum: float | int | None = None
    exclusiveMaximum: float | int | None = None
    minLength: int | None = None
    maxLength: int | None = None
    pattern: str | None = None


class StrategyMetadataResponse(BaseModel):
    name: str
    description: str
    parameters: dict[str, StrategyParameterMetadata]


class BacktestRunRequest(BaseModel):
    config_text: str = Field(min_length=1)
    format: Literal["json", "yaml"]


class BacktestRunResponse(BaseModel):
    output_path: str
    status: Literal["success", "partial_failure", "failure"]
    total_runs: int
    successful_runs: int
    failed_runs: int


class ServerInfoResponse(BaseModel):
    backtest_results_dir: str
    platform_settings_path: str


class SingleDayBacktestRequest(BaseModel):
    symbol: str = Field(min_length=1)
    date: date
    resolution: str = Field(description="Bar resolution such as 1m, 5m, 15m, 1h, or 1d")
    feed: Literal["iex", "sip", "otc"] = "iex"
    strategy: str
    strategy_params: dict[str, Any] = Field(default_factory=dict)
    broker: BrokerConfig | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("symbol must not be empty")
        return normalized

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        if value not in SUPPORTED_RESOLUTIONS:
            supported = ", ".join(SUPPORTED_RESOLUTIONS)
            raise ValueError(f"resolution must be one of: {supported}")
        return value


class SingleDayBacktestResult(BaseModel):
    status: Literal["success", "failed"]
    summary: RunSummary | None = None
    orders: list[OrderRecord] = Field(default_factory=list)
    trades: list[TradeRecord] = Field(default_factory=list)
    error: RunError | None = None


class SingleDayBacktestResponse(BaseModel):
    symbol: str
    date: date
    resolution: str
    cache_status: str
    bars: list[MarketDataRow]
    backtest: SingleDayBacktestResult


class BarsQueryParams(BaseModel):
    start_date: date
    stop_date: date
    resolution: str = Field(description="Bar resolution such as 1m, 5m, 15m, 1h, or 1d")
    feed: Literal["iex", "sip", "otc"] = "iex"
    force_refresh: bool = False

    @field_validator("resolution")
    @classmethod
    def validate_resolution(cls, value: str) -> str:
        if value not in SUPPORTED_RESOLUTIONS:
            supported = ", ".join(SUPPORTED_RESOLUTIONS)
            raise ValueError(f"resolution must be one of: {supported}")
        return value

    @model_validator(mode="after")
    def validate_dates(self) -> "BarsQueryParams":
        if self.start_date > self.stop_date:
            raise ValueError("start_date must be <= stop_date")
        return self


def create_app(
    cache_config: DataCacheConfig | None = None,
    output_dir: Path | None = None,
    log_file: Path | None = None,
) -> FastAPI:
    logger = configure_api_logging(log_file)
    app = FastAPI(title="Backtest Market Data API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_methods=["DELETE", "GET", "POST", "PUT"],
        allow_headers=["*"],
    )
    resolved_cache_config = cache_config or DataCacheConfig()
    resolved_output_dir = (output_dir or (Path(tempfile.gettempdir()) / "backtest-api-results")).resolve()
    backtest_jobs = BacktestJobService(BacktestResultRepository(resolved_output_dir), resolved_cache_config)
    settings_service = PlatformSettingsService(resolved_output_dir / "settings" / "platform-settings.json")

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("%s %s failed", request.method, request.url.path)
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/server/info", response_model=ServerInfoResponse)
    def get_server_info() -> ServerInfoResponse:
        return ServerInfoResponse(
            backtest_results_dir=str(resolved_output_dir),
            platform_settings_path=str(settings_service.path.resolve()),
        )

    @app.get("/strategies", response_model=list[StrategyMetadataResponse])
    def get_strategies() -> list[StrategyMetadataResponse]:
        return [
            StrategyMetadataResponse(
                name=spec.name,
                description=spec.description,
                parameters=_build_strategy_parameters(spec.params_model),
            )
            for spec in list_strategies()
        ]

    @app.post("/backtests", response_model=BacktestCreateResponse, status_code=status.HTTP_202_ACCEPTED)
    def create_backtest(payload: BacktestCreateRequest) -> BacktestCreateResponse:
        settings = settings_service.load()
        payload = payload.model_copy(
            update={
                "broker": payload.broker or settings.backtest_defaults.broker,
                "analyzers": payload.analyzers or settings.backtest_defaults.analyzers,
                "execution": payload.execution or settings.backtest_defaults.execution,
            }
        )
        return backtest_jobs.submit(payload)

    @app.get("/settings", response_model=PlatformSettings)
    def get_settings() -> PlatformSettings:
        return settings_service.load()

    @app.put("/settings", response_model=PlatformSettings)
    def put_settings(payload: PlatformSettings) -> PlatformSettings:
        return settings_service.save(payload)

    @app.get("/backtests", response_model=list[BacktestListItem])
    def list_backtests() -> list[BacktestListItem]:
        return backtest_jobs.list_backtests()

    @app.get("/backtests/{backtest_id}", response_model=BacktestDetailResponse)
    def get_backtest(backtest_id: str) -> BacktestDetailResponse:
        detail = backtest_jobs.get_detail(backtest_id)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"Backtest '{backtest_id}' not found")
        return detail

    @app.get("/backtests/{backtest_id}/status", response_model=BacktestStatusResponse)
    def get_backtest_status(backtest_id: str) -> BacktestStatusResponse:
        status_payload = backtest_jobs.get_status(backtest_id)
        if status_payload is None:
            raise HTTPException(status_code=404, detail=f"Backtest '{backtest_id}' not found")
        return status_payload

    @app.get("/backtests/{backtest_id}/report")
    def get_backtest_report(backtest_id: str) -> FileResponse:
        report_path = backtest_jobs.repository.report_path(backtest_id)
        if not report_path.exists():
            raise HTTPException(status_code=404, detail=f"Backtest report '{backtest_id}' not found")
        return FileResponse(
            report_path,
            media_type="application/json",
            filename=f"{backtest_id}.json",
        )

    @app.get("/backtests/{backtest_id}/config")
    def get_backtest_config(backtest_id: str) -> Response:
        yaml_text = backtest_jobs.repository.resolve_config_yaml(backtest_id)
        if yaml_text is None:
            raise HTTPException(status_code=404, detail=f"Backtest config '{backtest_id}' not found")
        return Response(
            content=yaml_text,
            media_type="application/x-yaml",
            headers={"Content-Disposition": f'inline; filename="{backtest_id}.yaml"'},
        )

    @app.delete("/backtests/{backtest_id}", status_code=status.HTTP_204_NO_CONTENT)
    def delete_backtest(backtest_id: str) -> None:
        if not backtest_jobs.delete(backtest_id):
            raise HTTPException(status_code=404, detail=f"Backtest '{backtest_id}' not found")

    @app.post("/backtests/run", response_model=BacktestRunResponse)
    def run_backtest(payload: BacktestRunRequest) -> BacktestRunResponse:
        try:
            config_raw = _parse_inline_backtest_config(payload)
            config = BacktestConfig.model_validate(config_raw)
        except (ValidationError, ValueError, json.JSONDecodeError, yaml.YAMLError) as exc:
            raise _validation_error(exc) from exc

        try:
            report = run_backtests(config, config_raw)
            output_path = _build_backtest_output_path(resolved_output_dir)
            write_backtest_report_json(report, output_path)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to execute backtest: {exc}") from exc

        return BacktestRunResponse(
            output_path=str(output_path),
            status=report.status,
            total_runs=report.total_runs,
            successful_runs=report.successful_runs,
            failed_runs=report.failed_runs,
        )

    @app.post("/backtests/single-day", response_model=SingleDayBacktestResponse)
    def run_single_day_backtest(payload: SingleDayBacktestRequest) -> SingleDayBacktestResponse:
        try:
            config_raw = _build_single_day_config_raw(payload)
            config = BacktestConfig.model_validate(config_raw)
        except (ValidationError, ValueError) as exc:
            raise _validation_error(exc) from exc

        data_source = AlpacaDataSource(
            type="alpaca",
            symbol=payload.symbol,
            interval=payload.resolution,
            feed=payload.feed,
        )
        try:
            frame, cache_status = build_alpaca_data_feed_with_cache(
                data_source,
                payload.date,
                payload.date,
                resolved_cache_config,
                force_refresh=False,
            )
        except RuntimeError as exc:
            raise _http_error_from_loader_error(exc) from exc

        try:
            report = run_backtests(config, config_raw)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=500, detail=f"Failed to execute backtest: {exc}") from exc

        result = report.results[0] if report.results else None
        if result is None or result.status == "failed":
            backtest = SingleDayBacktestResult(
                status="failed",
                summary=result.summary if result else None,
                orders=result.orders if result else [],
                trades=result.trades if result else [],
                error=result.error if result else RunError(type="BacktestError", message="Backtest produced no results"),
            )
        else:
            backtest = SingleDayBacktestResult(
                status="success",
                summary=result.summary,
                orders=result.orders,
                trades=result.trades,
                error=None,
            )

        return SingleDayBacktestResponse(
            symbol=payload.symbol,
            date=payload.date,
            resolution=payload.resolution,
            cache_status=cache_status,
            bars=_frame_to_rows(frame),
            backtest=backtest,
        )

    @app.get("/symbols/{symbol}/bars", response_model=MarketDataResponse)
    def get_symbol_bars(
        symbol: str,
        start_date: date = Query(...),
        stop_date: date = Query(...),
        resolution: str = Query(...),
        feed: Literal["iex", "sip", "otc"] = Query("iex"),
        force_refresh: bool = Query(False),
    ) -> MarketDataResponse:
        try:
            params = BarsQueryParams(
                start_date=start_date,
                stop_date=stop_date,
                resolution=resolution,
                feed=feed,
                force_refresh=force_refresh,
            )
        except ValidationError as exc:
            errors = [error["msg"] for error in exc.errors()]
            raise HTTPException(status_code=422, detail=errors) from exc
        normalized_symbol = symbol.upper()
        data_source = AlpacaDataSource(
            type="alpaca",
            symbol=normalized_symbol,
            interval=params.resolution,
            feed=params.feed,
        )

        try:
            frame, cache_status = build_alpaca_data_feed_with_cache(
                data_source,
                params.start_date,
                params.stop_date,
                resolved_cache_config,
                force_refresh=params.force_refresh,
            )
        except RuntimeError as exc:
            raise _http_error_from_loader_error(exc) from exc

        return MarketDataResponse(
            symbol=normalized_symbol,
            provider="alpaca",
            resolution=params.resolution,
            start_date=params.start_date,
            stop_date=params.stop_date,
            cache_status=cache_status,
            rows=_frame_to_rows(frame),
        )

    @app.post("/trading-contracts", response_model=TradingContractResponse, status_code=status.HTTP_201_CREATED)
    def create_trading_contract(
        payload: TradingContractCreate,
        session: Session = Depends(get_db_session),
    ) -> TradingContractResponse:
        record = to_contract_record(payload)
        session.add(record)
        session.commit()
        session.refresh(record)
        return TradingContractResponse.from_model(record)

    @app.get("/trading-contracts/active", response_model=list[TradingContractResponse])
    def get_active_trading_contracts(
        symbol: str | None = Query(None),
        strategy: str | None = Query(None),
        active_at: datetime | None = Query(None),
        session: Session = Depends(get_db_session),
    ) -> list[TradingContractResponse]:
        try:
            filters = TradingContractActiveQuery(symbol=symbol, strategy=strategy, active_at=active_at)
        except ValidationError as exc:
            errors = [error["msg"] for error in exc.errors()]
            raise HTTPException(status_code=422, detail=errors) from exc

        resolved_active_at = filters.active_at or datetime.now(timezone.utc)
        query = (
            select(TradingContract)
            .where(TradingContract.start_datetime <= resolved_active_at)
            .where(TradingContract.end_datetime > resolved_active_at)
            .order_by(TradingContract.start_datetime.asc())
        )
        if filters.symbol is not None:
            query = query.where(TradingContract.symbol == filters.symbol)
        if filters.strategy is not None:
            query = query.where(TradingContract.strategy == filters.strategy)

        contracts = session.execute(query).scalars().all()
        return [TradingContractResponse.from_model(contract) for contract in contracts]

    return app


def _frame_to_rows(frame: pd.DataFrame) -> list[MarketDataRow]:
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


def _build_strategy_parameters(params_model: type[BaseModel]) -> dict[str, StrategyParameterMetadata]:
    schema = params_model.model_json_schema()
    properties = schema.get("properties", {})
    required_fields = set(schema.get("required", []))
    parameters: dict[str, StrategyParameterMetadata] = {}

    for name, property_schema in properties.items():
        parameters[name] = StrategyParameterMetadata(
            type=property_schema["type"],
            default=property_schema.get("default"),
            required=name in required_fields,
            minimum=property_schema.get("minimum"),
            maximum=property_schema.get("maximum"),
            exclusiveMinimum=property_schema.get("exclusiveMinimum"),
            exclusiveMaximum=property_schema.get("exclusiveMaximum"),
            minLength=property_schema.get("minLength"),
            maxLength=property_schema.get("maxLength"),
            pattern=property_schema.get("pattern"),
        )

    return parameters


def _build_single_day_config_raw(payload: SingleDayBacktestRequest) -> dict[str, Any]:
    broker = payload.broker or BrokerConfig(cash=100_000.0)
    return {
        "runs": [
            {
                "run_id": f"ui_{payload.symbol}_{payload.date.isoformat()}",
                "start_date": payload.date.isoformat(),
                "end_date": payload.date.isoformat(),
                "data": {
                    "type": "alpaca",
                    "symbol": payload.symbol,
                    "interval": payload.resolution,
                    "feed": payload.feed,
                },
                "strategy": payload.strategy,
                "strategy_params": payload.strategy_params,
                "broker": broker.model_dump(),
                "analyzers": AnalyzerConfig(
                    include_equity_curve=False,
                    include_order_log=True,
                    include_trade_log=True,
                ).model_dump(),
            }
        ]
    }


def build_single_day_config(payload: SingleDayBacktestRequest) -> BacktestConfig:
    return BacktestConfig.model_validate(_build_single_day_config_raw(payload))


def _build_backtest_output_path(output_dir: Path) -> Path:
    return output_dir / f"{uuid.uuid4()}.json"


def _parse_inline_backtest_config(payload: BacktestRunRequest) -> dict[str, Any]:
    if payload.format == "json":
        data = json.loads(payload.config_text)
    else:
        data = yaml.safe_load(payload.config_text)
    if not isinstance(data, dict):
        raise ValueError("Config root must be an object")
    return data


def _validation_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ValidationError):
        detail = [error["msg"] for error in exc.errors()]
    else:
        detail = [str(exc)]
    return HTTPException(status_code=422, detail=detail)


def _http_error_from_loader_error(exc: RuntimeError) -> HTTPException:
    message = str(exc)
    if "Alpaca credentials missing" in message:
        return HTTPException(status_code=500, detail=message)
    if "Unsupported Alpaca interval" in message or "No Alpaca data found" in message:
        return HTTPException(status_code=400, detail=message)
    if "Alpaca request failed" in message or "Failed to reach Alpaca data API" in message:
        return HTTPException(status_code=502, detail=message)
    return HTTPException(status_code=500, detail=message)


app = create_app()
