from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260527_000004"
down_revision = "20260525_000003"
branch_labels = None
depends_on = None


def _json_type() -> sa.JSON:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    json_type = _json_type()

    op.create_table(
        "backtest_jobs",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("report_status", sa.String(length=32), nullable=True),
        sa.Column("total_runs", sa.Integer(), nullable=False),
        sa.Column("completed_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("successful_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("selection", json_type, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("execution_backend", sa.String(length=16), nullable=False, server_default="local"),
        sa.Column("workflow_name", sa.String(length=256), nullable=True),
        sa.Column("workflow_namespace", sa.String(length=128), nullable=True),
        sa.Column("config_path", sa.Text(), nullable=True),
        sa.Column("report_json_path", sa.Text(), nullable=True),
        sa.Column("report_parquet_path", sa.Text(), nullable=True),
        sa.Column("candidates_json_path", sa.Text(), nullable=True),
        sa.Column("candidates_parquet_path", sa.Text(), nullable=True),
        sa.Column("equity_parquet_path", sa.Text(), nullable=True),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_jobs_status_updated_at",
        "backtest_jobs",
        ["status", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_jobs_created_at",
        "backtest_jobs",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_jobs_created_at", table_name="backtest_jobs")
    op.drop_index("ix_backtest_jobs_status_updated_at", table_name="backtest_jobs")
    op.drop_table("backtest_jobs")
