from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260528_000010"
down_revision = "20260528_000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("backtest_jobs", sa.Column("name", sa.String(length=256), nullable=True))


def downgrade() -> None:
    op.drop_column("backtest_jobs", "name")
