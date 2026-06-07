"""add dataset jobs table

Revision ID: 20260607_000015
Revises: 20260605_000014
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_000015"
down_revision = "20260605_000014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dataset_jobs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("resolution", sa.String(length=16), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("argo_namespace", sa.String(length=128), nullable=True),
        sa.Column("argo_workflow_name", sa.String(length=256), nullable=True),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("output_dir", sa.Text(), nullable=False),
        sa.Column("dataset_parquet_path", sa.Text(), nullable=True),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index("ix_dataset_jobs_created_at", "dataset_jobs", ["created_at"])
    op.create_index("ix_dataset_jobs_status_updated_at", "dataset_jobs", ["status", "updated_at"])
    op.create_index("ix_dataset_jobs_symbol_created_at", "dataset_jobs", ["symbol", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_dataset_jobs_symbol_created_at", table_name="dataset_jobs")
    op.drop_index("ix_dataset_jobs_status_updated_at", table_name="dataset_jobs")
    op.drop_index("ix_dataset_jobs_created_at", table_name="dataset_jobs")
    op.drop_table("dataset_jobs")
