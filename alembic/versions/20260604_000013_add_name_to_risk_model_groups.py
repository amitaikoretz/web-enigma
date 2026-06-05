from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260604_000013"
down_revision = "20260604_000012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_model_groups", sa.Column("name", sa.String(length=128), nullable=True))


def downgrade() -> None:
    op.drop_column("risk_model_groups", "name")
