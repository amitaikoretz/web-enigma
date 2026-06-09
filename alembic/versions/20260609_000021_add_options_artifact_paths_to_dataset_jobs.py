"""add options artifact paths to dataset jobs

Revision ID: 20260609_000021
Revises: 20260608_000020
Create Date: 2026-06-09 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260609_000021"
down_revision = "20260608_000020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dataset_jobs", sa.Column("options_parquet_path", sa.Text(), nullable=True))
    op.add_column("dataset_jobs", sa.Column("options_manifest_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("dataset_jobs", "options_manifest_path")
    op.drop_column("dataset_jobs", "options_parquet_path")
