from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260607_000017"
down_revision = "20260607_000016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "market_overview_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=256), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("argo_namespace", sa.String(length=128), nullable=True),
        sa.Column("argo_workflow_name", sa.String(length=256), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=True),
        sa.Column("top_regime", sa.String(length=128), nullable=True),
        sa.Column("probabilities_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("fragility", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("contradiction_score", sa.Float(), nullable=False, server_default=sa.text("0")),
        sa.Column("pillar_scores_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("developments_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("freshness_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("params_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index(
        "ix_market_overview_snapshots_created_at",
        "market_overview_snapshots",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_market_overview_snapshots_status",
        "market_overview_snapshots",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_market_overview_snapshots_as_of",
        "market_overview_snapshots",
        ["as_of"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_market_overview_snapshots_as_of", table_name="market_overview_snapshots")
    op.drop_index("ix_market_overview_snapshots_status", table_name="market_overview_snapshots")
    op.drop_index("ix_market_overview_snapshots_created_at", table_name="market_overview_snapshots")
    op.drop_table("market_overview_snapshots")
