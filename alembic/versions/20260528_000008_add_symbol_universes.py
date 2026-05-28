"""Add symbol universes tables.

Revision ID: 20260528_000008
Revises: 20260527_000007
Create Date: 2026-05-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "20260528_000008"
down_revision = "20260527_000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "symbol_universes",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="registry"),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("provider_ref", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ux_symbol_universes_key", "symbol_universes", ["key"], unique=True)
    op.create_index("ix_symbol_universes_is_active", "symbol_universes", ["is_active"])
    op.create_index("ix_symbol_universes_kind", "symbol_universes", ["kind"])

    op.create_table(
        "symbol_universe_constituents",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("universe_id", sa.Uuid(), sa.ForeignKey("symbol_universes.id"), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_symbol_universe_constituents_universe_effective_from",
        "symbol_universe_constituents",
        ["universe_id", "effective_from"],
    )
    op.create_index(
        "ix_symbol_universe_constituents_universe_symbol",
        "symbol_universe_constituents",
        ["universe_id", "symbol"],
    )
    op.create_index("ix_symbol_universe_constituents_symbol", "symbol_universe_constituents", ["symbol"])

    op.create_table(
        "symbol_universe_refresh_runs",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("universe_id", sa.Uuid(), sa.ForeignKey("symbol_universes.id"), nullable=True),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stats", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_symbol_universe_refresh_runs_universe_started_at",
        "symbol_universe_refresh_runs",
        ["universe_id", "started_at"],
    )
    op.create_index(
        "ix_symbol_universe_refresh_runs_status_started_at",
        "symbol_universe_refresh_runs",
        ["status", "started_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_symbol_universe_refresh_runs_status_started_at", table_name="symbol_universe_refresh_runs")
    op.drop_index("ix_symbol_universe_refresh_runs_universe_started_at", table_name="symbol_universe_refresh_runs")
    op.drop_table("symbol_universe_refresh_runs")

    op.drop_index("ix_symbol_universe_constituents_symbol", table_name="symbol_universe_constituents")
    op.drop_index(
        "ix_symbol_universe_constituents_universe_symbol",
        table_name="symbol_universe_constituents",
    )
    op.drop_index(
        "ix_symbol_universe_constituents_universe_effective_from",
        table_name="symbol_universe_constituents",
    )
    op.drop_table("symbol_universe_constituents")

    op.drop_index("ix_symbol_universes_kind", table_name="symbol_universes")
    op.drop_index("ix_symbol_universes_is_active", table_name="symbol_universes")
    op.drop_index("ux_symbol_universes_key", table_name="symbol_universes")
    op.drop_table("symbol_universes")
