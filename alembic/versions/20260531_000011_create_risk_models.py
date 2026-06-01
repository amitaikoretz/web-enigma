from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260531_000011"
down_revision = "20260528_000010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "risk_model_groups",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("argo_namespace", sa.String(length=128), nullable=True),
        sa.Column("argo_workflow_name", sa.String(length=256), nullable=True),
        sa.Column("params_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("artifact_dir", sa.Text(), nullable=False),
        sa.Column("summary_metrics_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_risk_model_groups_created_at", "risk_model_groups", ["created_at"], unique=False)
    op.create_index("ix_risk_model_groups_status", "risk_model_groups", ["status"], unique=False)

    op.create_table(
        "risk_model_sources",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.String(length=64), sa.ForeignKey("risk_model_groups.id"), nullable=False),
        sa.Column("backtest_id", sa.String(length=64), sa.ForeignKey("backtest_jobs.id"), nullable=False),
        sa.Column("source_report_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_risk_model_sources_group_id", "risk_model_sources", ["group_id"], unique=False)
    op.create_index(
        "ux_risk_model_sources_group_backtest",
        "risk_model_sources",
        ["group_id", "backtest_id"],
        unique=True,
    )

    op.create_table(
        "risk_model_targets",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.String(length=64), sa.ForeignKey("risk_model_groups.id"), nullable=False),
        sa.Column("target_key", sa.String(length=64), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="running"),
        sa.Column("model_artifact_path", sa.Text(), nullable=True),
        sa.Column("metrics_json", sa.JSON(), nullable=True),
        sa.Column("dataset_manifest_path", sa.Text(), nullable=True),
        sa.Column("feature_columns_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_risk_model_targets_group_id", "risk_model_targets", ["group_id"], unique=False)
    op.create_index("ix_risk_model_targets_target_key", "risk_model_targets", ["target_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_risk_model_targets_target_key", table_name="risk_model_targets")
    op.drop_index("ix_risk_model_targets_group_id", table_name="risk_model_targets")
    op.drop_table("risk_model_targets")

    op.drop_index("ux_risk_model_sources_group_backtest", table_name="risk_model_sources")
    op.drop_index("ix_risk_model_sources_group_id", table_name="risk_model_sources")
    op.drop_table("risk_model_sources")

    op.drop_index("ix_risk_model_groups_status", table_name="risk_model_groups")
    op.drop_index("ix_risk_model_groups_created_at", table_name="risk_model_groups")
    op.drop_table("risk_model_groups")
