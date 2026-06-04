from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260604_000012"
down_revision = "20260531_000011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "risk_model_groups",
        sa.Column("family", sa.String(length=32), nullable=False, server_default="risk"),
    )
    op.create_index(
        "ix_risk_model_groups_family_created_at",
        "risk_model_groups",
        ["family", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_risk_model_groups_family_created_at", table_name="risk_model_groups")
    op.drop_column("risk_model_groups", "family")
