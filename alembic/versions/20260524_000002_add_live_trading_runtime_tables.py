from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260524_000002"
down_revision = "20260524_000001"
branch_labels = None
depends_on = None


def _json_type() -> sa.JSON:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    json_type = _json_type()

    op.create_table(
        "trade_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("symbol_key", sa.String(length=128), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("shard_id", sa.Integer(), nullable=False),
        sa.Column("strategy_name", sa.String(length=128), nullable=False),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("signal_hash", sa.String(length=128), nullable=False),
        sa.Column("signal_payload", json_type, nullable=False),
        sa.Column("intended_side", sa.String(length=16), nullable=False),
        sa.Column("intended_qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("intended_notional", sa.Numeric(18, 8), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("run_mode", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["trading_contracts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trade_intents_contract_created_at", "trade_intents", ["contract_id", "created_at"], unique=False)
    op.create_index("ix_trade_intents_symbol_key_created_at", "trade_intents", ["symbol_key", "created_at"], unique=False)
    op.create_index("ix_trade_intents_worker_created_at", "trade_intents", ["worker_id", "created_at"], unique=False)

    op.create_table(
        "broker_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("trade_intent_id", sa.Uuid(), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("symbol_key", sa.String(length=128), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("shard_id", sa.Integer(), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=False),
        sa.Column("broker_order_id", sa.String(length=128), nullable=True),
        sa.Column("broker_name", sa.String(length=32), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("filled_qty", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("remaining_qty", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("order_type", sa.String(length=32), nullable=False),
        sa.Column("time_in_force", sa.String(length=16), nullable=False),
        sa.Column("limit_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("stop_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("submission_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_broker_message", sa.Text(), nullable=True),
        sa.Column("broker_response", json_type, nullable=False),
        sa.Column("run_mode", sa.String(length=32), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_fill_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["trading_contracts.id"]),
        sa.ForeignKeyConstraint(["trade_intent_id"], ["trade_intents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ux_broker_orders_broker_client_order_id",
        "broker_orders",
        ["broker_name", "client_order_id"],
        unique=True,
    )
    op.create_index(
        "ux_broker_orders_broker_order_id",
        "broker_orders",
        ["broker_name", "broker_order_id"],
        unique=True,
    )
    op.create_index(
        "ix_broker_orders_symbol_key_status_submitted_at",
        "broker_orders",
        ["symbol_key", "status", "submitted_at"],
        unique=False,
    )
    op.create_index(
        "ix_broker_orders_contract_submitted_at",
        "broker_orders",
        ["contract_id", "submitted_at"],
        unique=False,
    )

    op.create_table(
        "broker_fills",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("broker_order_row_id", sa.Uuid(), nullable=True),
        sa.Column("broker_order_id", sa.String(length=128), nullable=False),
        sa.Column("client_order_id", sa.String(length=128), nullable=True),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("symbol_key", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=16), nullable=False),
        sa.Column("fill_qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("fill_price", sa.Numeric(18, 8), nullable=False),
        sa.Column("fill_notional", sa.Numeric(18, 8), nullable=True),
        sa.Column("raw_payload", json_type, nullable=False),
        sa.Column("run_mode", sa.String(length=32), nullable=False),
        sa.Column("fill_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["broker_order_row_id"], ["broker_orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_broker_fills_broker_order_fill_timestamp",
        "broker_fills",
        ["broker_order_id", "fill_timestamp"],
        unique=False,
    )
    op.create_index(
        "ix_broker_fills_symbol_key_fill_timestamp",
        "broker_fills",
        ["symbol_key", "fill_timestamp"],
        unique=False,
    )

    op.create_table(
        "positions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("symbol_key", sa.String(length=128), nullable=False),
        sa.Column("broker_name", sa.String(length=32), nullable=False),
        sa.Column("net_qty", sa.Numeric(18, 8), nullable=False, server_default="0"),
        sa.Column("avg_entry_price", sa.Numeric(18, 8), nullable=True),
        sa.Column("market_value", sa.Numeric(18, 8), nullable=True),
        sa.Column("cost_basis", sa.Numeric(18, 8), nullable=True),
        sa.Column("realized_pnl", sa.Numeric(18, 8), nullable=True),
        sa.Column("unrealized_pnl", sa.Numeric(18, 8), nullable=True),
        sa.Column("last_fill_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_details", json_type, nullable=False),
        sa.Column("run_mode", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_positions_broker_symbol_key", "positions", ["broker_name", "symbol_key"], unique=True)
    op.create_index("ix_positions_status_updated_at", "positions", ["status", "updated_at"], unique=False)

    op.create_table(
        "position_contract_allocations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("position_id", sa.Uuid(), nullable=False),
        sa.Column("contract_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_qty", sa.Numeric(18, 8), nullable=False),
        sa.Column("allocation_method", sa.String(length=32), nullable=False),
        sa.Column("allocation_metadata", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["trading_contracts.id"]),
        sa.ForeignKeyConstraint(["position_id"], ["positions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_position_contract_allocations_position_contract",
        "position_contract_allocations",
        ["position_id", "contract_id"],
        unique=False,
    )
    op.create_index(
        "ix_position_contract_allocations_contract_updated_at",
        "position_contract_allocations",
        ["contract_id", "updated_at"],
        unique=False,
    )

    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("broker_name", sa.String(length=32), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("mismatch_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", json_type, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_reconciliation_runs_scope_started_at",
        "reconciliation_runs",
        ["scope_type", "scope_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_reconciliation_runs_status_started_at",
        "reconciliation_runs",
        ["status", "started_at"],
        unique=False,
    )

    op.create_table(
        "worker_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("worker_id", sa.String(length=128), nullable=False),
        sa.Column("shard_id", sa.Integer(), nullable=True),
        sa.Column("contract_id", sa.Uuid(), nullable=True),
        sa.Column("symbol_key", sa.String(length=128), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["contract_id"], ["trading_contracts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_worker_events_worker_created_at", "worker_events", ["worker_id", "created_at"], unique=False)
    op.create_index(
        "ix_worker_events_event_type_created_at",
        "worker_events",
        ["event_type", "created_at"],
        unique=False,
    )
    op.create_index("ix_worker_events_symbol_key_created_at", "worker_events", ["symbol_key", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_worker_events_symbol_key_created_at", table_name="worker_events")
    op.drop_index("ix_worker_events_event_type_created_at", table_name="worker_events")
    op.drop_index("ix_worker_events_worker_created_at", table_name="worker_events")
    op.drop_table("worker_events")

    op.drop_index("ix_reconciliation_runs_status_started_at", table_name="reconciliation_runs")
    op.drop_index("ix_reconciliation_runs_scope_started_at", table_name="reconciliation_runs")
    op.drop_table("reconciliation_runs")

    op.drop_index("ix_position_contract_allocations_contract_updated_at", table_name="position_contract_allocations")
    op.drop_index("ix_position_contract_allocations_position_contract", table_name="position_contract_allocations")
    op.drop_table("position_contract_allocations")

    op.drop_index("ix_positions_status_updated_at", table_name="positions")
    op.drop_index("ux_positions_broker_symbol_key", table_name="positions")
    op.drop_table("positions")

    op.drop_index("ix_broker_fills_symbol_key_fill_timestamp", table_name="broker_fills")
    op.drop_index("ix_broker_fills_broker_order_fill_timestamp", table_name="broker_fills")
    op.drop_table("broker_fills")

    op.drop_index("ix_broker_orders_contract_submitted_at", table_name="broker_orders")
    op.drop_index("ix_broker_orders_symbol_key_status_submitted_at", table_name="broker_orders")
    op.drop_index("ux_broker_orders_broker_order_id", table_name="broker_orders")
    op.drop_index("ux_broker_orders_broker_client_order_id", table_name="broker_orders")
    op.drop_table("broker_orders")

    op.drop_index("ix_trade_intents_worker_created_at", table_name="trade_intents")
    op.drop_index("ix_trade_intents_symbol_key_created_at", table_name="trade_intents")
    op.drop_index("ix_trade_intents_contract_created_at", table_name="trade_intents")
    op.drop_table("trade_intents")
