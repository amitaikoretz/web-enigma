from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_000007"
down_revision = "20260527_000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("backtest_jobs", sa.Column("labels_parquet_path", sa.Text(), nullable=True))
    op.add_column("backtest_jobs", sa.Column("features_parquet_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("backtest_jobs", "features_parquet_path")
    op.drop_column("backtest_jobs", "labels_parquet_path")
