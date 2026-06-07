from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260605_000014"
down_revision = "20260604_000013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("risk_model_groups", sa.Column("feature_run_id", sa.String(length=64), nullable=True))
    op.create_index(
        "ix_risk_model_groups_feature_run_id",
        "risk_model_groups",
        ["feature_run_id"],
        unique=False,
    )
    op.create_table(
        "daily_index_feature_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("benchmark_symbol", sa.String(length=32), nullable=True),
        sa.Column("decision_times_json", sa.JSON(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("argo_namespace", sa.String(length=128), nullable=True),
        sa.Column("argo_workflow_name", sa.String(length=256), nullable=True),
        sa.Column("params_json", sa.JSON(), nullable=False),
        sa.Column("artifact_dir", sa.Text(), nullable=False),
        sa.Column("manifest_path", sa.Text(), nullable=True),
        sa.Column("features_parquet_path", sa.Text(), nullable=True),
        sa.Column("labels_parquet_path", sa.Text(), nullable=True),
        sa.Column("summary_metrics_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index(
        "ix_daily_index_feature_runs_created_at",
        "daily_index_feature_runs",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_daily_index_feature_runs_status",
        "daily_index_feature_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_daily_index_feature_runs_symbol",
        "daily_index_feature_runs",
        ["symbol"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_index_feature_runs_symbol", table_name="daily_index_feature_runs")
    op.drop_index("ix_daily_index_feature_runs_status", table_name="daily_index_feature_runs")
    op.drop_index("ix_daily_index_feature_runs_created_at", table_name="daily_index_feature_runs")
    op.drop_table("daily_index_feature_runs")
    op.drop_index("ix_risk_model_groups_feature_run_id", table_name="risk_model_groups")
    op.drop_column("risk_model_groups", "feature_run_id")

