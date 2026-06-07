"""add params_json to dataset_jobs

Revision ID: 20260607_000018
Revises: 20260607_000017
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_000018"
down_revision = "20260607_000017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dataset_jobs",
        sa.Column("params_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.alter_column("dataset_jobs", "params_json", server_default=None)


def downgrade() -> None:
    op.drop_column("dataset_jobs", "params_json")
