from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260527_000006"
down_revision = "20260527_000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("backtest_jobs", sa.Column("orders_parquet_path", sa.Text(), nullable=True))
    op.add_column("backtest_jobs", sa.Column("trades_parquet_path", sa.Text(), nullable=True))
    op.add_column("backtest_jobs", sa.Column("rejections_parquet_path", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("backtest_jobs", "rejections_parquet_path")
    op.drop_column("backtest_jobs", "trades_parquet_path")
    op.drop_column("backtest_jobs", "orders_parquet_path")
