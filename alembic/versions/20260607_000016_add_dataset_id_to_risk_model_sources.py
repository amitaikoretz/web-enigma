"""add dataset_id to risk model sources

Revision ID: 20260607_000016
Revises: 20260607_000015
Create Date: 2026-06-07 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_000016"
down_revision = "20260607_000015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("risk_model_sources", sa.Column("dataset_id", sa.String(length=64), nullable=True))
    if bind.dialect.name != "sqlite":
        op.create_foreign_key(
            "fk_risk_model_sources_dataset_id_dataset_jobs",
            "risk_model_sources",
            "dataset_jobs",
            ["dataset_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "sqlite":
        op.drop_constraint("fk_risk_model_sources_dataset_id_dataset_jobs", "risk_model_sources", type_="foreignkey")
    op.drop_column("risk_model_sources", "dataset_id")
