from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_000005"
down_revision = "20260527_000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("backtest_jobs", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("backtest_jobs", sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("backtest_jobs", "finished_at")
    op.drop_column("backtest_jobs", "started_at")
