"""add backtest type and request payload to backtest jobs

Revision ID: 20260614_000022
Revises: 20260609_000021
Create Date: 2026-06-14 12:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260614_000022"
down_revision = "20260609_000021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "backtest_jobs",
        sa.Column("backtest_type", sa.String(length=32), nullable=False, server_default="classic"),
    )
    op.add_column(
        "backtest_jobs",
        sa.Column("request_payload_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backtest_jobs", "request_payload_json")
    op.drop_column("backtest_jobs", "backtest_type")
