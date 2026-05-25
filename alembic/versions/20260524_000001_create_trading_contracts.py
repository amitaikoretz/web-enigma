from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260524_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    json_type = (
        postgresql.JSONB(astext_type=sa.Text())
        if bind.dialect.name == "postgresql"
        else sa.JSON()
    )

    op.create_table(
        "trading_contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("strategy", sa.String(length=128), nullable=False),
        sa.Column("strategy_params", json_type, nullable=False),
        sa.Column("start_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_datetime", sa.DateTime(timezone=True), nullable=False),
        sa.Column("maximum_trade_size", sa.Numeric(18, 8), nullable=False),
        sa.Column("total_invested", sa.Numeric(18, 8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trading_contracts_symbol_strategy",
        "trading_contracts",
        ["symbol", "strategy"],
        unique=False,
    )
    op.create_index(
        "ix_trading_contracts_start_datetime",
        "trading_contracts",
        ["start_datetime"],
        unique=False,
    )
    op.create_index(
        "ix_trading_contracts_end_datetime",
        "trading_contracts",
        ["end_datetime"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trading_contracts_end_datetime", table_name="trading_contracts")
    op.drop_index("ix_trading_contracts_start_datetime", table_name="trading_contracts")
    op.drop_index("ix_trading_contracts_symbol_strategy", table_name="trading_contracts")
    op.drop_table("trading_contracts")
