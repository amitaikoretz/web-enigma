from __future__ import annotations

import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_alembic_upgrade_creates_trading_contracts_table(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database_path = tmp_path / "contracts.db"
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    os.environ.pop("DATABASE_URL", None)

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}", future=True)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("trading_contracts")}
    indexes = {index["name"] for index in inspector.get_indexes("trading_contracts")}
    runtime_tables = {
        "trade_intents",
        "broker_orders",
        "broker_fills",
        "positions",
        "position_contract_allocations",
        "reconciliation_runs",
        "worker_events",
    }

    assert {
        "id",
        "symbol",
        "strategy",
        "strategy_params",
        "start_datetime",
        "end_datetime",
        "maximum_trade_size",
        "total_invested",
        "revision",
        "deleted_at",
        "created_at",
    }.issubset(columns)
    assert "ix_trading_contracts_deleted_at" in indexes
    assert "ix_trading_contracts_symbol_strategy" in indexes
    assert "ix_trading_contracts_start_datetime" in indexes
    assert "ix_trading_contracts_end_datetime" in indexes
    assert runtime_tables.issubset(set(inspector.get_table_names()))


def test_alembic_upgrade_creates_backtest_jobs_table(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database_path = tmp_path / "backtests.db"
    alembic_ini = Path(__file__).resolve().parents[1] / "alembic.ini"
    config = Config(str(alembic_ini))
    config.set_main_option("script_location", str(alembic_ini.parent / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    os.environ.pop("DATABASE_URL", None)

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}", future=True)
    inspector = inspect(engine)
    assert "backtest_jobs" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("backtest_jobs")}
    assert {
        "id",
        "status",
        "report_json_path",
        "candidates_parquet_path",
        "equity_parquet_path",
        "orders_parquet_path",
        "trades_parquet_path",
        "rejections_parquet_path",
        "created_at",
        "updated_at",
    }.issubset(columns)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO trading_contracts (
                    id, symbol, strategy, strategy_params, start_datetime, end_datetime,
                    maximum_trade_size, total_invested
                ) VALUES (
                    :id, :symbol, :strategy, :strategy_params, :start_datetime, :end_datetime,
                    :maximum_trade_size, :total_invested
                )
                """
            ),
            {
                "id": "aa0d74d7-7a8d-4fe4-a20f-b5d30e935001",
                "symbol": "AAPL",
                "strategy": "sma_cross",
                "strategy_params": '{"fast": 5, "slow": 10}',
                "start_datetime": "2026-05-24T10:00:00+00:00",
                "end_datetime": "2026-05-24T16:00:00+00:00",
                "maximum_trade_size": 1000,
                "total_invested": 2500,
            },
        )
        stored = connection.execute(text("SELECT strategy_params FROM trading_contracts")).scalar_one()
        connection.execute(
            text(
                """
                INSERT INTO trade_intents (
                    id, contract_id, symbol, symbol_key, worker_id, shard_id, strategy_name,
                    signal_type, signal_hash, signal_payload, intended_side, intended_qty,
                    status, run_mode
                ) VALUES (
                    :id, :contract_id, :symbol, :symbol_key, :worker_id, :shard_id, :strategy_name,
                    :signal_type, :signal_hash, :signal_payload, :intended_side, :intended_qty,
                    :status, :run_mode
                )
                """
            ),
            {
                "id": "aa0d74d7-7a8d-4fe4-a20f-b5d30e935002",
                "contract_id": "aa0d74d7-7a8d-4fe4-a20f-b5d30e935001",
                "symbol": "AAPL",
                "symbol_key": "AAPL",
                "worker_id": "worker-1",
                "shard_id": 0,
                "strategy_name": "sma_cross",
                "signal_type": "entry",
                "signal_hash": "abc123",
                "signal_payload": '{"bar":"2026-05-24T10:01:00+00:00"}',
                "intended_side": "buy",
                "intended_qty": 10,
                "status": "created",
                "run_mode": "paper_live",
            },
        )
        runtime_status = connection.execute(text("SELECT status FROM trade_intents")).scalar_one()

    assert "fast" in stored
    assert runtime_status == "created"
