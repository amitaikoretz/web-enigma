from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260525_000003"
down_revision = "20260524_000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "trading_contracts",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "trading_contracts",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_trading_contracts_deleted_at",
        "trading_contracts",
        ["deleted_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_trading_contracts_deleted_at", table_name="trading_contracts")
    op.drop_column("trading_contracts", "deleted_at")
    op.drop_column("trading_contracts", "revision")
