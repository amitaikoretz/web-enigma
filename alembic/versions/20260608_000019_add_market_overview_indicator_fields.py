from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260608_000019"
down_revision = "20260607_000017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "market_overview_snapshots",
        sa.Column("market_indicators_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "market_overview_snapshots",
        sa.Column("watch_next_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "market_overview_snapshots",
        sa.Column("methodology_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("market_overview_snapshots", "methodology_json")
    op.drop_column("market_overview_snapshots", "watch_next_json")
    op.drop_column("market_overview_snapshots", "market_indicators_json")
